# Cron externo para Climate Radar

Configurar solamente después de varias ejecuciones manuales correctas.

## Token granular

Crear un token exclusivo:

```text
Nombre:
climate-radar-cron

Acceso:
Only selected repositories
→ climate-radar

Permiso:
Actions
→ Read and write
```

No guardar el token en el repositorio.

## Trabajo

Nombre:

```text
ClimateProyectar - Radares cada 10 minutos
```

URL:

```text
https://api.github.com/repos/mtgproyect/climate-radar/actions/workflows/actualizar-radares.yml/dispatches
```

Método:

```text
POST
```

Horario:

```cron
*/10 * * * *
```

Zona horaria:

```text
America/Argentina/Buenos_Aires
```

Cuerpo:

```json
{
  "ref": "main"
}
```

Encabezados:

```text
Accept: application/vnd.github+json
Authorization: Bearer TOKEN_DE_RADAR
X-GitHub-Api-Version: 2026-03-10
Content-Type: application/json
User-Agent: cron-job-org-climateproyectar
```

Una prueba correcta devuelve:

```text
HTTP 204
```
