# iMessage Scheduler

A simple iMessage scheduling system composed of a web frontend, a Django backend with Celery, and a macOS gateway that sends messages through Messages.app.

The system is intentionally split so that all scheduling, retries, throttling, and state live on the server, while actual message sending is delegated to a trusted macOS machine that is signed into iMessage.

---

## Local Development

You run three things:

1. Docker services (backend, Celery, Postgres, Redis)
2. Frontend dev server
3. macOS gateway process

---

### Requirements

- Docker and Docker Compose
- Node 18 or newer
- Python 3.11 or newer
- macOS with Messages.app signed in

---

### Start Backend Stack

Navigate to the the infrastructure directory and run docker compose:

    cd infrastructure
    docker compose up -d --build

On first startup, the backend container will automatically:

    - Wait for Postgres to be ready

    - Apply all Django migrations

    - Optionally create an admin user if configured via environment variables

Useful commands:

    docker compose ps
    docker compose logs -f api
    docker compose logs -f worker
    docker compose logs -f beat

Health check:

    curl http://127.0.0.1:8000/api/health/

---

### Database Migrations and Admin User

Migrations are applied automatically when the backend container starts. No manual action is required.

Optional admin user creation can be disabled by removing the following environment variables on the api service in infrastructure/docker-compose.yml:

    CREATE_SUPERUSER=1

    DJANGO_SUPERUSER_USERNAME

    DJANGO_SUPERUSER_EMAIL

    DJANGO_SUPERUSER_PASSWORD

If these variables are not set, no superuser is created.

---

### Start Frontend

Navigate to the frontend directory:

    cd apps/web/scheduler-ui

    npm install
    npm run dev

Vite proxies /api to the Django backend so the browser can call the API without CORS issues.

---

### Start Gateway (macOS)

First, cd into the gateway directory:

    cd apps/gateway

    python3 gateway.py

Optional environment variables:

- API_BASE_URL (default <http://127.0.0.1:8000>)
- GATEWAY_ID (default mac-1)
- POLL_SECONDS (default 5)

Example:

    API_BASE_URL=http://127.0.0.1:8000 GATEWAY_ID=mac-1 POLL_SECONDS=2 python3 gateway.py

---

## Architecture

### Components

Frontend (React + Vite)

- Used to create scheduled messages.
- Displays message history and delivery status.
- Communicates with the backend using /api/\* through a Vite proxy.

Backend (Django + Django REST Framework)

- Stores messages and status events in Postgres.
- Exposes APIs for:
  - Creating and managing scheduled messages
  - Gateway claim and report flows
  - Aggregated statistics for dashboards

Celery (Worker + Beat)

- Periodically evaluates scheduled messages.
- Determines when messages are eligible to be sent.
- Prepares messages for gateway pickup.
- Does not send iMessages directly.

Gateway (macOS only)

- Long running Python script.
- Polls the backend for prepared messages.
- Uses AppleScript via osascript to send iMessages through Messages.app.
- Reports success or failure back to the backend.

---

## How the System Works

### 1. Message Creation

A user creates a scheduled message in the frontend.

Frontend:

- Calls createMessage()
- Sends POST /api/messages/

Backend:

- Handled by ScheduledMessageViewSet.create()
- Uses ScheduledMessageCreateSerializer
- Persists a ScheduledMessage with fields such as:
  - to_handle
  - body
  - scheduled_for
  - status (initially QUEUED)

---

### 2. Scheduler Tick (Celery Beat)

Celery Beat periodically triggers the scheduler task.

Example beat configuration in Celery:

    app.conf.beat_schedule = {
      "scheduler-tick-every-5-seconds": {
        "task": "scheduler.tasks.scheduler_tick",
        "schedule": 5.0,
      }
    }

The worker executes scheduler.tasks.scheduler_tick().

Current behavior:

- Finds messages that are due.
- Applies throttling rules using DeliveryThrottle.
- Marks eligible messages as prepared for gateway pickup by setting:
  - status = ACCEPTED
  - claimed_by = "gateway_pending"
  - claimed_at = None

This step does not send messages. It only transitions state.

---

### 3. Gateway Claim

The gateway polls the backend for work.

Request:

- POST /api/gateway/claim/
- Body: {"gateway_id": "mac-1"}

Backend:

- Handled by GatewayClaimAPIView.post()
- Calls claim_next_message() in scheduler/services.py

The service first attempts to claim messages already prepared by Celery by selecting rows with:

- status = ACCEPTED
- claimed_by = "gateway_pending"
- claimed_at is null
- scheduled_for <= now

The row is locked using select_for_update(skip_locked=True).

If a message is found:

- claimed_at is set to the current time
- claimed_by is set to the gateway ID
- The API returns a payload containing to_handle and body

If no message is available:

- The API returns 204 No Content

---

### 4. Sending the iMessage

The gateway receives a claimed message and sends it via Messages.app.

Gateway logic:

- Calls send_imessage(to_handle, body)
- Internally runs osascript with an AppleScript that sends the message from the currently signed in Messages account

---

### 5. Reporting Status

After attempting to send, the gateway reports the result back to the backend.

Request:

- POST /api/gateway/report/
- Includes:
  - message_id
  - status (SENT, FAILED, etc.)
  - optional error metadata

Backend:

- Handled by GatewayReportAPIView.post()
- Updates the ScheduledMessage row
- Creates a MessageStatusEvent entry

Failure handling:

- attempt_count is incremented
- last_error is recorded
- If under the retry limit:
  - status is reset to QUEUED
  - scheduled_for is moved into the future using exponential backoff

The retry delay helper computes:

- delay = base \* (2 \*\* (attempt_count - 1))
- delay is capped at max_delay

---

## Verifying the System

1. Start Docker services, frontend, and gateway.
2. Create a message scheduled for now or earlier.
3. Observe the pipeline.

Celery preparation:

- Check worker logs for scheduler_tick activity and ready messages.

Gateway claim:

- POST to /api/gateway/claim/
- 200 OK means a message was returned
- 204 No Content means nothing is ready

Gateway send and report:

- Gateway logs show CLAIMED and SENT
- Message status updates in the backend accordingly

---

## Message Statuses

- QUEUED: waiting for scheduled time
- ACCEPTED: prepared or claimed
- SENT: send succeeded
- DELIVERED: delivery confirmed if implemented
- RECEIVED: receipt confirmed if implemented
- FAILED: send failed permanently
- CANCELED: user canceled before send

All transitions are recorded in MessageStatusEvent.

---

## Dashboard Stats

Endpoint:

- GET /api/stats/messages-by-status/

Backend:

- MessageStatusStatsAPIView
- Aggregates ScheduledMessage rows grouped by status

Serializer:

- MessageStatusCountSerializer

Frontend:

- fetchMessageStatusStats() calls the stats endpoint to populate charts

### Real-time message status updates for chart (SSE)

The UI updates using Server-Sent Events (SSE), keeping one long-lived HTTP connection open to the backend

#### What happens end-to-end

1. **The browser opens a stream**

   - The frontend calls `new EventSource("/api/stream/messages/")`, sending a request that stays open.

2. **The backend keeps the connection open**

   - It continuously _yields_ small text chunks in SSE format like:
     - `event: message`
     - `data: {...json...}`
   - It also sends occasional `ping` events so proxies and browsers do not drop the connection.

3. **Backend changes publish an event**

   - Whenever something important changes on the backend (message created, canceled, accepted by scheduler/gateway, status reported), the backend publishes a small JSON event into Redis (a pub/sub channel).
   - Redis acts as the “broadcast pipe”. Anything that publishes to that channel will be seen by the stream process.

4. **The stream forwards Redis events to the browser**

   - The stream endpoint is subscribed to that Redis pub/sub channel.
   - When it receives a Redis message, it immediately writes it out to the open SSE connection as an SSE `event: message`.

5. **The frontend reacts instantly**
   - When the browser receives an SSE `message` event, the frontend runs your handler.
   - Your handler re-fetches:
     - the messages list (table)
     - the stats endpoint (chart)
     - the selected message (detail view), if one is selected
   - The UI and chart reflect the backend state.

---

## Notes and Constraints

- Docker containers cannot send iMessages.
- The gateway must run on macOS and be signed into iMessage.
- All queueing, retries, and state live on the backend.
- The gateway is a stateless sender that reports results back to the server.
