import asyncio
import serial_asyncio
import os
import sys

class DistanceSensor:
    # Class variable to track sensors and their line positions
    sensor_count = 0
    sensors = []
    display_initialized = False
    
    def __init__(self, port, baudrate=115200, command=0x55, read_interval=0.1, name=None):
        self.port = port
        self.baudrate = baudrate
        self.command = command
        self.read_interval = read_interval
        self.transport = None
        self.protocol = None
        self.buffer = bytearray()
        self.latest_distance = None
        self.counter = 0
        
        # Assign a line position for this sensor
        self.sensor_id = DistanceSensor.sensor_count
        DistanceSensor.sensor_count += 1
        DistanceSensor.sensors.append(self)
        
        # Extract just the port number for shorter display
        self.port_name = os.path.basename(port)
        # Use the provided name or port_name if none provided
        self.name = name if name else self.port_name
        self.debug = False

    @classmethod
    def setup_display(cls):
        """Create the initial display layout with lines for each sensor"""
        if cls.display_initialized:
            return
            
        # Clear screen and move to top
        print("\033[2J\033[H", end="")
        
        # Print header
        print("==== Distance Sensor Array ====")
        print("Sensor readings (updated in real time):")
        print("")
        
        # Create a line for each sensor
        for sensor in cls.sensors:
            sensor_info = f"Sensor {sensor.name} ({sensor.port_name}):"
            print(f"{sensor_info:<30} Waiting for data...")
        
        # Add a footer line for general messages
        print("\n(Press Ctrl+C to exit)")
        
        cls.display_initialized = True

    def update_display(self, message):
        """Update this sensor's line without affecting other sensors"""
        if not DistanceSensor.display_initialized:
            DistanceSensor.setup_display()
            
        # Calculate this sensor's line position (header + 3 + sensor_id)
        line_pos = 4 + self.sensor_id
        
        # Save position, move to sensor's line, clear line, write message, restore position
        sys.stdout.write(f"\033[s\033[{line_pos};1H\033[K{message}\033[u")
        sys.stdout.flush()

    async def connect(self):
        self.transport, self.protocol = await serial_asyncio.create_serial_connection(
            asyncio.get_event_loop(),
            lambda: SerialProtocol(self),
            self.port,
            baudrate=self.baudrate
        )
        await asyncio.sleep(1)  # Wait for connection to stabilize
        await self.flush_input()
        
        # Initialize the display if not already done
        if not DistanceSensor.display_initialized:
            DistanceSensor.setup_display()
            
        sensor_info = f"Sensor {self.name} ({self.port_name}):"
        self.update_display(f"{sensor_info:<30} Connected, waiting for data...")

    async def flush_input(self):
        self.transport.serial.reset_input_buffer()
        if self.debug:
            sensor_info = f"Sensor {self.name} ({self.port_name}):"
            self.update_display(f"{sensor_info:<30} Flushed input buffer")

    async def read_loop(self):
        while True:
            await self.send_command()
            # Wait a bit for the response, similar to Arduino code
            await asyncio.sleep(0.1)

    async def send_command(self):
        if self.transport:
            self.transport.write(bytes([self.command]))

    def process_data(self, data):
        self.buffer.extend(data)
        
        # Process complete packets
        while len(self.buffer) >= 4:
            # Look for the start byte (0xFF)
            if self.buffer[0] == 0xff:
                if len(self.buffer) >= 4:  # Make sure we have a complete packet
                    packet = self.buffer[:4]
                    
                    # Calculate checksum like in Arduino code
                    cs = (packet[0] + packet[1] + packet[2]) & 0xFF
                    
                    if packet[3] == cs:
                        # Calculate distance like in Arduino code
                        self.latest_distance = (packet[1] << 8) + packet[2]
                        self.counter += 1
                        
                        # Format output on this sensor's dedicated line with fixed width for name/port
                        feet = self.latest_distance * 0.00328084  # Convert to feet like in Arduino
                        sensor_info = f"Sensor {self.name} ({self.port_name}):"
                        self.update_display(f"{sensor_info:<30} Distance = {self.latest_distance} mm ({feet:.2f} ft) [count: {self.counter}]")
                    else:
                        # Print error on dedicated line with fixed width
                        sensor_info = f"Sensor {self.name} ({self.port_name}):"
                        self.update_display(f"{sensor_info:<30} Checksum error: expected {packet[3]}, got {cs}")
                    
                    # Remove processed packet
                    self.buffer = self.buffer[4:]
                else:
                    # Not enough data yet, wait for more
                    break
            else:
                # If not starting with 0xFF, remove this byte and continue
                # We'll only log this if debug mode is enabled
                if self.debug:
                    sensor_info = f"Sensor {self.name} ({self.port_name}):"
                    self.update_display(f"{sensor_info:<30} Skipping byte: {self.buffer[0]:#04x}")
                self.buffer = self.buffer[1:]

    def set_debug(self, debug=True):
        """Enable or disable debug output"""
        self.debug = debug

class SerialProtocol(asyncio.Protocol):
    def __init__(self, sensor):
        self.sensor = sensor

    def data_received(self, data):
        if data and self.sensor.debug:
            sensor_info = f"Sensor {self.sensor.name} ({self.sensor.port_name}):"
            self.sensor.update_display(f"{sensor_info:<30} Received: {' '.join([f'{b:#04x}' for b in data])}")
        self.sensor.process_data(data)