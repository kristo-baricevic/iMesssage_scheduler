from rest_framework.renderers import BaseRenderer

class EventStreamRenderer(BaseRenderer):
    media_type = "text/event-stream"
    format = "event-stream"
    charset = None

    def render(self, data, media_type=None, renderer_context=None):
        return data
