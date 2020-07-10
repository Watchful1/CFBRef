import prometheus_client

active_games = prometheus_client.Gauge('active_games', "Current number of active games")
objects_replied = prometheus_client.Counter('objects_replied', "Count of messages/comments replied to")


def init(port):
	prometheus_client.start_http_server(port)
