# Climate Radar

Servicio modular de radares meteorológicos para ClimateProyectar.

## Cobertura inicial

```text
3 mosaicos
21 radares individuales
24 productos totales
```

Los nombres corresponden a los productos publicados actualmente en la página
de radares del Servicio Meteorológico Nacional.

## Sin almacenamiento de imágenes

Este repositorio nunca descarga ni guarda imágenes meteorológicas.

```text
GitHub
→ código, configuración y manifiesto JSON

Servidor oficial del SMN
→ archivos PNG/JPG/WebP de radar
```

El contrato publicado declara:

```json
{
  "storage": {
    "mode": "remote_urls_only",
    "stored_image_count": 0
  }
}
```

Además:

- `.gitignore` bloquea extensiones de imagen;
- las pruebas fallan si aparece una imagen dentro del repositorio;
- el navegador usa `referrerpolicy="no-referrer"`.

## Primera ejecución

```text
Actions
→ Actualizar radares SMN
→ Run workflow
```

Después abrir:

```text
https://mtgproyect.github.io/climate-radar/
https://mtgproyect.github.io/climate-radar/manifiesto.json
```

## Automatización externa

El workflow no tiene cron interno. Se dispara desde cron-job.org.

Endpoint:

```text
https://api.github.com/repos/mtgproyect/climate-radar/actions/workflows/actualizar-radares.yml/dispatches
```

Cuerpo:

```json
{
  "ref": "main"
}
```

Frecuencia inicial recomendada, después de varias pruebas manuales:

```cron
*/10 * * * *
```

El script no modifica el manifiesto si el SMN todavía no publicó cuadros o
estados nuevos.
