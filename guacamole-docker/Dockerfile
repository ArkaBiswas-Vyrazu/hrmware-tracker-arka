FROM alpine:latest as base

FROM base as build
RUN echo -e '#!/bin/sh\n\
echo Hello world from $(whoami)! In order to get your application running in a container, take a look at the comments in the Dockerfile to get started.'\
> /bin/hello.sh
RUN chmod +x /bin/hello.sh

FROM base AS final

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser
USER appuser

COPY --from=build /bin/hello.sh /bin/

ENTRYPOINT [ "/bin/hello.sh" ]
