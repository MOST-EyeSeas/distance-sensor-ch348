import asyncio
import serial_asyncio

class DistanceSensor:
    def __init__(self, port, baudrate=115200, command=0x55, read_interval=0.1):
        self.port = port
        self.baudrate = baudrate
        self.command = command
        self.read_interval = read_interval
        self.transport = None
        self.protocol = None
        self.buffer = bytearray()
        self.latest_distance = None
        self.counter = 0

    async def connect(self):
        self.transport, self.protocol = await serial_asyncio.create_serial_connection(
            asyncio.get_event_loop(),
            lambda: SerialProtocol(self),
            self.port,
            baudrate=self.baudrate
        )
        await asyncio.sleep(1)  # Wait for connection to stabilize
        await self.flush_input()

    async def flush_input(self):
        self.transport.serial.reset_input_buffer()
        print(f"Flushed input buffer for sensor on {self.port}")

    async def read_loop(self):
        while True:
            await self.send_command()
            await asyncio.sleep(self.read_interval)

    async def send_command(self):
        if self.transport:
            self.transport.write(bytes([self.command]))

    def process_data(self, data):
        self.buffer.extend(data)
        while len(self.buffer) >= 4:
            if self.buffer[0] == 0xff:
                packet = self.buffer[:4]
                checksum = sum(packet[:3]) & 0xFF
                if packet[3] == checksum:
                    self.latest_distance = (packet[1] << 8) | packet[2]
                    self.counter += 1
                    print(f"Sensor {self.port}: Distance = {self.latest_distance} mm", self.counter)
                self.buffer = self.buffer[4:]
            else:
                self.buffer = self.buffer[1:]

class SerialProtocol(asyncio.Protocol):
    def __init__(self, sensor):
        self.sensor = sensor

    def data_received(self, data):
        self.sensor.process_data(data)