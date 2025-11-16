FROM haproxy:2.9-alpine

# Copy HAProxy configuration
COPY haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg

# Expose ports
# 8080 - Load balanced gateway traffic
# 8404 - HAProxy stats dashboard
EXPOSE 8080 8404

# Health check
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg || exit 1

# Run HAProxy
CMD ["haproxy", "-f", "/usr/local/etc/haproxy/haproxy.cfg"]
