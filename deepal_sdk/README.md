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

### Integración de Home Assistant

En la integración elige la plataforma **International (Europe)** y pega los tokens Access, Refresh y
CAC que imprimen los ejemplos de login. Las entradas internacionales son de solo lectura (sensores y
binary sensors); los comandos remotos de la plataforma internacional todavía no están soportados.

## Estructura del Proyecto

- `deepal/client.py`: Cliente HTTP asíncrono principal (`DeepalClient`).
- `deepal/intl.py`: Cliente de la plataforma internacional (`DeepalIntlClient`, login por correo).
- `deepal/models/`: Modelos Pydantic para `Vehicle`, `VehicleCondition`, `AuthToken`, etc.
- `deepal/endpoints.py`: Constantes de URLs y endpoints de la API.
- `examples/`: Scripts de demostración para login y consulta de estado.
