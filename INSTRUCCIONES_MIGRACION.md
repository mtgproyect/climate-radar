# Activar Climate Radar

## 1. Reemplazar el esqueleto

Descomprimir este paquete y copiar todo su contenido dentro de la copia local
del repositorio:

```text
mtgproyect/climate-radar
```

Permitir que se reemplacen:

```text
README.md
.gitignore
docs/
.github/
```

Se agregarán:

```text
config/
scripts/
tests/
requirements.txt
INSTRUCCIONES_MIGRACION.md
CRON_JOB_ORG.md
```

## 2. Eliminar el workflow viejo

Si todavía existe, eliminar:

```text
.github/workflows/validar-esqueleto.yml
```

Debe quedar como workflow operativo:

```text
.github/workflows/actualizar-radares.yml
```

## 3. Subir con GitHub Desktop

Mensaje:

```text
Activar catálogo modular de radares SMN
```

Después:

```text
Commit to main
Push origin
```

## 4. Verificar Pages

Configuración:

```text
Settings
→ Pages
→ Deploy from a branch
→ main
→ /docs
```

## 5. Primera prueba manual

```text
Actions
→ Actualizar radares SMN
→ Run workflow
```

La primera ejecución valida en vivo los identificadores configurados contra
los inventarios oficiales.

Resultado esperado:

```text
Consultar inventarios oficiales  ✓
Validar publicación              ✓
Guardar manifiesto               ✓
pages build and deployment       ✓
```

## 6. Abrir la página

```text
https://mtgproyect.github.io/climate-radar/
```

Y el manifiesto:

```text
https://mtgproyect.github.io/climate-radar/manifiesto.json
```

Comprobar:

```json
{
  "storage": {
    "mode": "remote_urls_only",
    "stored_image_count": 0
  }
}
```

## 7. No conectar aún el sitio V2

Primero realizar dos o tres ejecuciones manuales verdes y revisar:

```text
Mosaico Argentina
Mosaico Centro
Mosaico Norte
Ezeiza
Córdoba
algún radar del norte
algún radar del sur
```

Después se configura cron-job.org y se activa la fuente en ClimateProyectar V2.
