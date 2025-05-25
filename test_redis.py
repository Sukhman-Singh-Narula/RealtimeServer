import redis
r = redis.Redis(host='localhost', port=6379, db=0)
print(r.ping())  # Returns True if connected
