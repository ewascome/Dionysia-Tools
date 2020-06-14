# Pull from Python
FROM python:3-alpine
MAINTAINER Eric Wascome "eric@wascome.net"
RUN apk update && apk upgrade && apk add tzdata

# Clone from Git Repo
COPY . /Dionysia-Tools

# Install Dionysia-Tools
RUN apk add --no-cache gcc \
                       libffi-dev \
                       musl-dev \
                       openssl-dev
RUN pip3 install ./Dionysia-Tools

VOLUME ["/config"]

ENV CRONFILE /config/tasks.cron
ENV CONFIGFILE /config/config.json

COPY ./entrypoint.sh /usr/local/bin
RUN chmod +x /usr/local/bin/entrypoint.sh
CMD /usr/local/bin/entrypoint.sh
