# build: docker build -t busypy .
# run:
# --------------------------------------
# Two stage build,
# 1) python base image with gcc to build python modules
#
FROM python:3.6-alpine

RUN apk update && \
    apk add build-base gcc g++ musl-dev linux-headers

ADD requirements.txt /
RUN pip3 install -r requirements.txt

# --------------------------------------
# 2) copy over the python install with compiled modules...
#
FROM python:3.6-alpine
COPY --from=0 /usr/local/lib/python3.6/ /usr/local/lib/python3.6/

RUN apk add libstdc++

WORKDIR /cpu_load
ADD *.py /cpu_load/

ENTRYPOINT ["python"]
