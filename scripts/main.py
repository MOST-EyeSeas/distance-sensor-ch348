import asyncio
from sensor import DistanceSensor

async def run_sensors_simultaneously(sensors):
    await asyncio.gather(*(sensor.read_loop() for sensor in sensors))

async def run_sensors_sequentially(sensors):
    while True:
        for sensor in sensors:
            await sensor.send_command()
            await asyncio.sleep(0.1)  # Wait for response
        await asyncio.sleep(0.1)  # Delay between rounds

async def main():
    # Create sensor instances
    sensor1 = DistanceSensor('/dev/ttyCH9344USB0')
    sensor2 = DistanceSensor('/dev/ttyCH9344USB1')  # Adjust port as needed

    # Connect to sensors
    await asyncio.gather(sensor1.connect(), sensor2.connect())

    # Choose running mode
    mode = input("Enter 'sim' for simultaneous or 'seq' for sequential mode: ")

    try:
        if mode == 'sim':
            await run_sensors_simultaneously([sensor1, sensor2])
        elif mode == 'seq':
            await run_sensors_sequentially([sensor1, sensor2])
        else:
            print("Invalid mode. Exiting.")
    except asyncio.CancelledError:
        pass
    finally:
        # Close connections
        for sensor in [sensor1, sensor2]:
            if sensor.transport:
                sensor.transport.close()

if __name__ == "__main__":
    asyncio.run(main())