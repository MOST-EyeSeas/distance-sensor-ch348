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
    all_sensors = []
    
    sensor1 = DistanceSensor('/dev/ttyCH9344USB7')
    all_sensors.append(sensor1)

    sensor2 = DistanceSensor('/dev/ttyCH9344USB6')  # Adjust port as needed
    all_sensors.append(sensor2)

    sensor3 = DistanceSensor('/dev/ttyCH9344USB5')  # Adjust port as needed
    all_sensors.append(sensor3)
    
    sensor4 = DistanceSensor('/dev/ttyCH9344USB4')  # Adjust port as needed
    all_sensors.append(sensor4)



    # Connect to sensors
    # await asyncio.gather(sensor1.connect(), sensor2.connect(), sensor3.connect(), sensor4.connect())
    # await asyncio.gather(sensor4.connect())
    [await sensor.connect() for sensor in all_sensors]

    # Choose running mode
    mode = input("Enter 'sim' for simultaneous or 'seq' for sequential mode: ")

    try:
        if mode == 'sim':
            # await run_sensors_simultaneously([sensor1, sensor2, sensor3, sensor4])
            # await run_sensors_simultaneously([sensor4])
            await run_sensors_simultaneously(all_sensors)
        elif mode == 'seq':
            # await run_sensors_sequentially([sensor1, sensor2, sensor3, sensor4])
            # await run_sensors_sequentially([sensor4])
            await run_sensors_sequentially(all_sensors)
        else:
            print("Invalid mode. Exiting.")
    except asyncio.CancelledError:
        pass
    finally:
        # Close connections
        # for sensor in [sensor1, sensor2, sensor3, sensor4]:
        # for sensor in [sensor4]:
        for sensor in all_sensors:
            if sensor.transport:
                sensor.transport.close()

if __name__ == "__main__":
    asyncio.run(main())