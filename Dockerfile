# steps: docker build -t busypy .
#        docker images (get the hash_value)
#        docker tag <hash_value> martinguthriedocker/busypy
#        docker push martinguthriedocker/busypy
#
# --------------------------------------
# Two stage build,
# 1) python base image with gcc to build python modules
#
FROM python:3.6-alpine

RUN apk update && \
    apk add build-base gcc g++ musl-dev linux-headers

ADD requirements_docker.txt /
RUN pip3 install -r requirements_docker.txt
RUN pip3 uninstall -y pip wheel
RUN rm -r /usr/local/lib/python3.6/site-packages/setuptools*

# --------------------------------------
# 2) copy over the python install with compiled modules...
#
FROM python:3.6-alpine
RUN pip3 uninstall -y pip wheel
RUN rm -r /usr/local/lib/python3.6/site-packages/setuptools*

COPY --from=0 /usr/local/lib/python3.6/site-packages/ /usr/local/lib/python3.6/site-packages/

RUN apk add libstdc++

WORKDIR /cpu_load
ADD *.py /cpu_load/

ENTRYPOINT ["python"]
# docker run -it [martinguthriedocker/]busypy busypy.py --help
# or
# docker run -it [martinguthriedocker/]busypy busypyserver.py --help
