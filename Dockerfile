FROM python:3.7-alpine

RUN  pip install stackuchin==1.5.1

VOLUME /project

WORKDIR /project

ENTRYPOINT ["/bin/sh", "-c"]

CMD ["stackuchin", "help"]