#!/bin/sh
set -e

echo "Waiting for Postgres..."
until python3 -c "import os, socket; socket.create_connection((os.environ['POSTGRES_HOST'], int(os.environ.get('POSTGRES_PORT','5432'))), 2).close()" >/dev/null 2>&1; do
  sleep 1
done

echo "Running migrations..."
until python3 manage.py migrate --noinput; do
  sleep 1
done

if [ "$CREATE_SUPERUSER" = "1" ]; then
  python3 manage.py shell -c "from django.contrib.auth import get_user_model; import os; User=get_user_model(); u=os.environ['DJANGO_SUPERUSER_USERNAME']; e=os.environ['DJANGO_SUPERUSER_EMAIL']; p=os.environ['DJANGO_SUPERUSER_PASSWORD']; User.objects.filter(username=u).exists() or User.objects.create_superuser(u,e,p)"
fi

exec "$@"
