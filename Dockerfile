FROM python:3.12
RUN pip3 install pyserial pyserial-asyncio
RUN apt-get update && apt-get install -y kmod

WORKDIR /home
RUN git clone https://github.com/MOST-EyeSeas/ch9344ser_linux.git
WORKDIR /home/ch9344ser_linux/driver
RUN apt-get update
# RUN apt-get install -y \
#     build-essential \
#     linux-headers-generic
# RUN make
# RUN make load


# Copy entrypoint script
RUN apt-get install -y sudo
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /workspace

RUN echo "source /entrypoint.sh" >> ~/.bashrc

ENTRYPOINT ["/entrypoint.sh"]