# The chat UI: static files served by nginx as a non-root user on port 8080, with a
# read-only root filesystem (nginx.conf writes only under /tmp, an emptyDir). Context: ui/
FROM nginxinc/nginx-unprivileged:1.29.8-alpine

USER root
# Alpine security fixes for the Trivy gate; drop the default site config we do not use.
RUN apk upgrade --no-cache && rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html
# 101 is the image's unprivileged nginx user.
USER 101
EXPOSE 8080
# Start nginx directly, skipping the entrypoint scripts that try to rewrite /etc/nginx.
ENTRYPOINT ["nginx", "-g", "daemon off;"]
