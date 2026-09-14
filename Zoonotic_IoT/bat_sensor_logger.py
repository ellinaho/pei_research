# bat_sensor_logger.py — minimal fixes

import time
import csv
from datetime import datetime

import board
import busio

import adafruit_scd4x
import adafruit_sgp30
import adafruit_sht4x
import adafruit_ds3231
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_pm25.i2c import PM25_I2C

# --- I2C (keep default 100kHz; you can slow in /boot/config.txt if needed) ---
i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)

# --- ADS1115 (two devices at 0x48, 0x49). Slow them down for stability. ---
ads_48 = ADS.ADS1115(i2c, address=0x48)
ads_49 = ADS.ADS1115(i2c, address=0x49)
for adc in (ads_48, ads_49):
    adc.data_rate = 8            # slowest SPS -> robust on long/shifted buses
    adc.gain = 1                 # ±4.096 V full-scale

mq_sensors = {
    "MQ-4 (Methane)"      : AnalogIn(ads_48, 0),
    "MQ-9 (Carbon Monoxide)": AnalogIn(ads_48, 1),
    "MQ-135 (Air Quality)": AnalogIn(ads_48, 2),
    "MQ-137 (Ammonia)"    : AnalogIn(ads_48, 3),
    "SEN0571 (Odor)"      : AnalogIn(ads_49, 0),
    "MiCS 5526 (VOC)"     : AnalogIn(ads_49, 3),
}

# --- SCD41 ---
scd41 = adafruit_scd4x.SCD4X(i2c)
scd41.start_periodic_measurement()

# --- SGP30 (use live readings; init IAQ; set humidity if desired) ---
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
sgp30.iaq_init()
# Optional humidity compensation (adjust to your conditions)
try:
    sgp30.set_iaq_relative_humidity(celsius=22.1, relative_humidity=44)
except Exception:
    pass

# --- SHT41 ---
sht41 = adafruit_sht4x.SHT4x(i2c)

# --- DS3231 ---
ds3231 = adafruit_ds3231.DS3231(i2c)
# do once! comment out later
ds3231.datetime = time.struct_time(datetime.now().timetuple())

# --- PM2.5 sensor ---
reset_pin = None
pm25 = PM25_I2C(i2c, reset_pin)

# --- CSV setup ---
first_timestamp = (
    f"{ds3231.datetime.tm_year:04d}-"
    f"{ds3231.datetime.tm_mon:02d}-"
    f"{ds3231.datetime.tm_mday:02d}_"
    f"{ds3231.datetime.tm_hour:02d}-"
    f"{ds3231.datetime.tm_min:02d}-"
    f"{ds3231.datetime.tm_sec:02d}"
)
csv_filename = f"sensor_log_{first_timestamp}.csv"

def calculate_resistance(v_out, v_circuit=5.0, r_load=10000.0):
    # Assumes MQ sensor forms a divider: V_out = V_circuit * (R_L / (R_S + R_L))
    # R_S = R_L * (V_circuit - V_out) / V_out
    if v_out is None or v_out <= 0.0:
        return None
    return ((v_circuit - v_out) / v_out) * r_load

print(f"Logging sensor data to {csv_filename}... Ctrl+C to stop.")
with open(csv_filename, mode="w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "Timestamp (ms)",
        "MQ-4 V", "MQ-9 V", "MQ-135 V", "MQ-137 V", "SEN0571 V", "MiCS5526 V",
        "MQ-4 R_s", "MQ-9 R_s", "MQ-135 R_s", "MQ-137 R_s", "SEN0571 R_s", "MiCS5526 R_s",
        "SCD41 CO2 ppm", "SCD41 Temp C", "SCD41 RH %",
        "SGP30 TVOC ppb", "SGP30 eCO2 ppm",
        "SHT41 Temp C", "SHT41 RH %",
        "PM1.0 env", "PM2.5 env", "PM10 env"
    ])

    try:
        while True:
            now = ds3231.datetime
            timestamp = f"{now.tm_year:04d}-{now.tm_mon:02d}-{now.tm_mday:02d} " \
                f"{now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

            # --- MQ reads (add tiny delay between reads to be kind to the bus) ---
            mq_values = []
            for ch in mq_sensors.values():
                try:
                    mq_values.append(ch.voltage)
                except Exception:
                    mq_values.append(None)
                time.sleep(0.01)  # 10 ms between channel reads

            mq_resistances = [calculate_resistance(v) for v in mq_values]

            # --- SCD41 ---
            scd41_co2 = scd41_temp = scd41_hum = None
            try:
                scd41_co2 = scd41.CO2
                scd41_temp = scd41.temperature
                scd41_hum = scd41.relative_humidity
            except Exception:
                # restart sequence if needed
                try:
                    scd41.stop_periodic_measurement()
                    time.sleep(0.1)
                    scd41.start_periodic_measurement()
                except Exception:
                    pass

            # --- SGP30 live readings ---
            sgp30_tvoc = sgp30_eco2 = None
            try:
                # per Adafruit API: first 15s stabilize; then call every second
                sgp30_tvoc = sgp30.TVOC
                sgp30_eco2 = sgp30.eCO2
            except Exception:
                pass

            # --- SHT41 ---
            sht41_temp = sht41_hum = None
            try:
                sht41_temp = sht41.temperature
                sht41_hum = sht41.relative_humidity
            except Exception:
                try:
                    sht41 = adafruit_sht4x.SHT4x(i2c)
                except Exception:
                    pass

            # --- PM2.5 ---
            pm1_0 = pm2_5 = pm10 = None
            try:
                aq = pm25.read()
                pm1_0 = aq.get("pm10 env")
                pm2_5 = aq.get("pm25 env")
                pm10  = aq.get("pm100 env")
            except Exception:
                pass

            row = [
                timestamp,
                *mq_values, *mq_resistances,
                scd41_co2, scd41_temp, scd41_hum,
                sgp30_tvoc, sgp30_eco2,
                sht41_temp, sht41_hum,
                pm1_0, pm2_5, pm10,
            ]
            w.writerow(row)
            f.flush()
            print(row)

            # small pacing so we’re not hammering the bus
            time.sleep(1.0)

    except KeyboardInterrupt:
        print(f"\nStopping sensor logging. Data saved to {csv_filename}.")
