#!/bin/bash -xe
. ./hooks/env  # (1)
docker build \  # (2)
	${VERSION:+--build-arg "VERSION=$VERSION"} \  # (3)
	-t $IMAGE_NAME .  # (4)

