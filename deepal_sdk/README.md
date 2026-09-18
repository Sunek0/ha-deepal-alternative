# Deepal Python SDK

Python SDK asíncrono para interactuar con la API de telemática y control remoto de vehículos **Changan Deepal** (S05 Max, S07, SL03, L07).

## Características

- ⚡ **Asíncrono:** Construido sobre `httpx` y `asyncio`.
- 🔐 **Autenticación:** Login por SMS code en la plataforma SDA, bind de OAuth tokens y login por código de verificación enviado por correo en la plataforma internacional (`DeepalIntlClient`).
- 🚗 **Telemática del vehículo:** Consulta de batería (SOC %), autonomía (km), odómetro acumulado (`CdcTotMilg`), estado de puertas, ventanas, climatización y neumáticos.
- 🎛️ **Control Remoto:** Comandos para bloqueo de puertas, climatización remota y estado del cargador.
- 📐 **Tipado estricto:** Modelos de datos validados con Pydantic v2.

## Instalación

```bash
pip install -e .
```

Los ejemplos de `examples/` se pueden ejecutar directamente con cualquier intérprete que tenga las
dependencias del SDK, sin necesidad de instalarlo antes:

```bash
python deepal_sdk/examples/basic_status.py
```

## Ejemplo de Uso

```python
import asyncio
from deepal import DeepalClient

async def main():
    async with DeepalClient(access_token="TU_TOKEN_AQUI") as client:
        # Listar vehículos
        vehicles = await client.get_vehicles()
        for car in vehicles:
            print(f"Coche: {car.series_name} | VIN: {car.vin}")
            
            # Consultar telemática
            cond = await client.get_vehicle_condition(car.car_id)
            print(f"Batería: {cond.battery.soc_percentage}%")
            print(f"Autonomía: {cond.battery.remaining_range_km} km")
            print(f"Odómetro: {cond.total_odometer_km} km")

asyncio.run(main())
```

## Login por correo (plataforma internacional)

La app My Changan/Deepal europea autentica con un código de verificación enviado al correo. El
`DeepalIntlClient` implementa ese flujo contra el gateway internacional (`m.iov.changanauto.com.de`),
cifrando el correo con la clave pública RSA de la app:

```python
import asyncio
from deepal import DeepalIntlClient

async def main():
    async with DeepalIntlClient(country="ES", language="es_ES") as client:
        await client.request_email_code("tu-correo@ejemplo.com")
        code = input("Código recibido por correo: ")
        token = await client.login_with_email_code("tu-correo@ejemplo.com", code)
        print(f"Access Token: {token.access_token}")
        print(f"Refresh Token: {token.refresh_token}")

asyncio.run(main())
```

También hay un ejemplo listo para ejecutar:

```bash
python deepal_sdk/examples/email_login_example.py
```

## Login por teléfono/SMS (plataforma internacional)

Si tu cuenta de la app My Changan está registrada con un número de teléfono, usa el flujo SMS
internacional. El código de país se envía sin el prefijo `+` (el SDK lo elimina si lo incluyes) y el
número debe ser nacional, sin prefijo de país; el ejemplo deduce el código de país a partir del país
para los mercados soportados:

```python
import asyncio
from deepal import DeepalIntlClient

async def main():
    async with DeepalIntlClient(country="ES", language="es_ES") as client:
        await client.request_sms_code("600000000", "34")
        code = input("Código recibido por SMS: ")
        token = await client.login_with_sms_code("600000000", code, "34")
        print(f"Access Token: {token.access_token}")

asyncio.run(main())
```

Ejemplo ejecutable:

```bash
python deepal_sdk/examples/sms_login_example.py
```

## Telemetría internacional

`DeepalIntlClient` también lee vehículos y estado (SOC, autonomía, odómetro, puertas y clima) y
refresca la sesión cuando el access token caduca:

```python
import asyncio
from deepal import DeepalIntlClient

async def main():
    async with DeepalIntlClient(country="ES") as client:
        client.access_token = "TU_ACCESS_TOKEN"
        client.refresh_token = "TU_REFRESH_TOKEN"
        client.cac_token = "TU_CAC_TOKEN"

        vehicles = await client.get_vehicles()
        for car in vehicles:
            cond = await client.get_vehicle_condition(car.car_id)
            print(f"{car.series_name}: {cond.battery.soc_percentage}% | {cond.total_odometer_km} km")

        await client.refresh_tokens()

asyncio.run(main())
```

La condición internacional incluye además presión y alarma de neumáticos (`cond.tires`), nivel de calor y
ventilación por asiento (`cond.seats`), posición de las ventanillas (`cond.windows`) y estado y nivel de
la calefacción del volante (`cond.climate.steering_wheel_heater_on` / `steering_wheel_heater_level`).

### Integración de Home Assistant

Añade la integración y elige la plataforma **International (Europe)**: el flujo hace el login real
en Home Assistant (código por email o SMS), genera el par de claves de firma y guarda los tokens,
el `user_id` y el país. Si la sesión caduca, Home Assistant pedirá reautenticarse. En las opciones
de la entrada puedes ajustar el intervalo de sondeo, el PIN de control remoto y el registro de
tráfico API redactado (útil para diagnosticar).

Los vehículos con backend MQTT (Deepal S05) usan la telemetría MQTT cuando la entrada tiene
`user_id`; si el gateway CA rechaza la cuenta, la integración avisa y continúa con la condición
REST. Los comandos remotos del S05 están deshabilitados por defecto: actívalos con la opción
experimental **"Enable experimental remote controls for MQTT vehicles (S05)"** en las opciones de
la entrada. No están verificados contra un coche real, así que úsalos con cuidado.

### Control del clima (plataforma internacional)

Para habilitar el control del aire acondicionado, el login debe haber generado la clave privada (el
flujo de la integración lo hace automáticamente). Aparecerá una entidad `climate` por vehículo con
encendido/apagado y temperatura objetivo entre 16 y 30 °C. El SDK también permite enviar el comando
directamente:

```python
await client.control_air_conditioner("CAR_ID", enabled=True, target_temp_c=22.0)
```

## Estructura del Proyecto

- `deepal/client.py`: Cliente HTTP asíncrono principal (`DeepalClient`).
- `deepal/intl.py`: Cliente de la plataforma internacional (`DeepalIntlClient`, login por correo).
- `deepal/models/`: Modelos Pydantic para `Vehicle`, `VehicleCondition`, `AuthToken`, etc.
- `deepal/endpoints.py`: Constantes de URLs y endpoints de la API.
- `examples/`: Scripts de demostración para login y consulta de estado.
