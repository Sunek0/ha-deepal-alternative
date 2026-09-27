# Guía completa: cuenta secundaria e instalación de Deepal Alternative

Guía paso a paso para conectar tu coche Changan/Deepal a Home Assistant con la integración
**Deepal Alternative**. Cubre el proceso completo: desde la creación de la cuenta secundaria en la
app My Changan hasta la instalación de la integración con HACS y su configuración.

## Índice

1. [Por qué usar una cuenta secundaria](#por-qué-usar-una-cuenta-secundaria)
2. [Requisitos previos](#requisitos-previos)
3. [Parte 1: cuenta secundaria en My Changan](#parte-1-cuenta-secundaria-en-my-changan)
4. [Parte 2: instalación de la integración](#parte-2-instalación-de-la-integración)
5. [Notas y solución de problemas](#notas-y-solución-de-problemas)

## Por qué usar una cuenta secundaria

La integración inicia sesión en la plataforma oficial de My Changan. Una misma cuenta no puede
mantener dos sesiones activas a la vez: si Home Assistant entra con tu cuenta principal, es posible
que se cierre la sesión en la app del móvil, y si vuelves a entrar en la app, se invalida la sesión
de Home Assistant.

La solución recomendada es crear una **cuenta secundaria**, compartir el coche desde la cuenta
principal y usar solo la secundaria en Home Assistant. Así tu cuenta principal sigue funcionando con
normalidad en el teléfono.

## Requisitos previos

- Un vehículo Deepal compatible (S05, S07) vinculado a una cuenta de My Changan.
- Acceso a la app **My Changan** con la cuenta principal.
- Un email o número de teléfono distinto para la cuenta secundaria.
- Home Assistant 2026.3.0 o superior.
- [HACS](https://hacs.xyz/docs/use/download/download/) instalado. Si aún no lo tienes, sigue las
  instrucciones oficiales de instalación en <https://hacs.xyz/docs/use/download/download/>.

## Parte 1: cuenta secundaria en My Changan

### 1. Crear la cuenta secundaria

1. Abre la app **My Changan** y crea una cuenta nueva con un email o un número de teléfono
   diferente al de tu cuenta principal.
2. Anota las credenciales (email/teléfono y código de acceso): serán las que uses en Home Assistant.

### 2. Compartir el vehículo desde la cuenta principal

1. Cierra la cuenta secundaria e inicia sesión en la app con la **cuenta principal**.
2. Pulsa en el botón **compartir** de la pantalla principal.
3. Invita a la cuenta secundaria que acabas de crear, indicando un periodo de validez permanente.

### 3. Aceptar el acceso y crear la contraseña de control

1. Cierra la sesión de la **cuenta principal** en la app e inicia sesión en la app con la **cuenta secundaria**.
2. Acepta el acceso al coche compartido.
3. Ve al **centro personal** (perfil) y pulsa en **Mi vehículo**.
4. Selecciona el coche compartido.
5. Pulsa en **Contraseña de control del vehículo** y crea una contraseña (PIN). Anótala: es el PIN
   que pedirá Home Assistant para los comandos de puertas, ventanillas y maletero.

> Si no encuentras esa opción en tu versión de la app, intenta bajar las ventanillas desde la app:
> te pedirá crear el PIN de control. Créalo y comprueba que el comando funciona.

### 4. Volver a la cuenta principal

1. Cierra la sesión de la cuenta secundaria y vuelve a iniciar sesión con la **cuenta principal**
   en el móvil.
2. La cuenta principal queda como propietaria del vehículo; la secundaria se usa solo en Home
   Assistant.

## Parte 2: instalación de la integración

### 5. Instalar HACS (si aún no lo tienes)

HACS es el gestor de integraciones personalizadas de Home Assistant. Si todavía no lo tienes
instalado, sigue la guía oficial: <https://hacs.xyz/docs/use/download/download/>. Una vez instalado,
aparecerá la pestaña **HACS** en la barra lateral de Home Assistant.

### 6. Añadir el repositorio a HACS

1. En Home Assistant, entra en la pestaña **HACS**.
2. Abre el menú de tres puntos (⋮) de la esquina superior derecha y elige
   **Repositorios personalizados**.
3. Pega la URL del repositorio:
   `https://github.com/Sunek0/ha-deepal-alternative`
4. En **Categoría**, selecciona **Integración** y pulsa **Añadir**.

### 7. Instalar Deepal Alternative y reiniciar

1. En HACS, busca **Deepal Alternative** (puedes usar el buscador de la pestaña o la categoría
   **Integraciones**).
2. Abre la ficha y pulsa **Descargar**.
3. **Reinicia Home Assistant** para cargar la integración nueva.

### 8. Añadir la integración

1. Ve a **Ajustes → Dispositivos y servicios**.
2. Pulsa **Añadir integración** y busca **Deepal Alternative**.
3. En **Plataforma**, elige **International (Europe)** (la opción SDA (China) es solo para cuentas
   de China continental con access token).
4. En **Método de login**, elige cómo accede tu cuenta secundaria:
   - **Email code**: se envía un código de verificación al email.
   - **Phone/SMS code**: se envía un código por SMS al móvil.
5. Rellena los datos del formulario:
   - **País de venta**: el país registrado en tu cuenta de My Changan (por ejemplo, España).
   - **Email** o **Número de móvil** (sin prefijo) de la cuenta **secundaria**.
6. Espera el código de verificación (email o SMS) e introdúcelo en **Código de verificación**.
7. La integración valida la cuenta y crea un dispositivo por vehículo. Listo.

### 9. Guardar el PIN de control remoto

Este paso **sólo es necesario** para poder usar los comandos firmados (bloqueo de puertas, ventanillas y
maletero) y para que Home Assistant cree sus entidades:

1. Ve a **Ajustes → Dispositivos y servicios → Deepal Alternative**.
2. Pulsa **Configurar**.
3. En **PIN de control remoto**, introduce la contraseña que creaste en el paso 3 con la cuenta
   secundaria.
4. Guarda. Las entidades de puertas, ventanillas y maletero aparecerán en el dispositivo del coche.

### 10. Comprobar que funciona

- Abre la página del dispositivo del vehículo: deberías ver los sensores de batería, autonomía,
  carga y demás telemetría.
- Prueba un comando seguro (por ejemplo, encender las luces o el clima) y confirma que el coche
  responde.
- Los comandos que dependen del PIN (puertas, ventanillas, maletero) que creamos con la cuenta secundaria-

## Notas y solución de problemas

- **No puedo controlar nada**: comprueba primero si la app oficial puede hacerlo con la misma
  cuenta. El coche a veces rechaza los comandos remotos hasta que se ha conducido unos minutos.
- **"Remote control PIN is not set" aunque ya guardé el PIN**: el PIN no se creó con la cuenta que
  usa Home Assistant. Inicia sesión en la app con la cuenta secundaria, crea el PIN (paso 3) y
  vuelve a guardarlo en las opciones de la integración.
- **Home Assistant pide reautenticarse**: la sesión se invalidó desde la app u otro dispositivo.
  Vuelve a iniciar sesión; con la cuenta secundaria es mucho menos frecuente.
- **Los valores parecen antiguos**: el coche solo reporta telemetría cuando está despierto; la
  integración muestra la última lectura conocida hasta que vuelve a reportar.
- **Aviso**: proyecto no oficial, sin relación con Changan Automobile. Los comandos remotos actúan
  sobre el coche real: asegúrate de que es seguro antes de usar cerraduras, ventanillas, maletero,
  clima, luces o claxon.
