import prometheus_client

active_games = prometheus_client.Gauge('bot_objects', "Current number of active games")
objects_replied = prometheus_client.Counter('bot_replies', "Count of messages/comments replied to")
reply_latency = prometheus_client.Summary('bot_latency_seconds', "Seconds delay to reply to a message/comment")
gist_ratelimit = prometheus_client.Gauge('gist_requests_remaining', "How many requests to github we have left")
gist_event = prometheus_client.Counter('gist_event', "How many requests to github we have left", ['type', 'method'])
gist_queue = prometheus_client.Gauge('gist_queue', "How many requests to github are queued")


def init(port):
	prometheus_client.start_http_server(port)
