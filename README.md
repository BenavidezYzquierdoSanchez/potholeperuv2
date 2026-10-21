# Baches Perú 2.0 — Análisis vial con cuatro modelos YOLO

Plataforma web en español: Bootstrap/JavaScript + FastAPI + Ultralytics. Selección S43, S44, V1 y SM45. No subir checkpoints desconocidos: los `.pt` se deserializan al cargarlos.

## Instalación local (Python 3.11 recomendado)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Abrir http://127.0.0.1:8000. API interactiva: `/docs`. Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`.

## Docker

`docker compose up --build -d` y acceder a `http://localhost:8000`. Para exposición pública usar un proxy HTTPS, control de acceso, copias de seguridad, límite de peticiones y almacenamiento privado. En `.env` establecer `BACHES_API_KEY=clave-larga-aleatoria` (el navegador permite ingresar la misma clave). No publique el servicio abierto con la clave vacía.

## Funcionalidades

- Imagen con máscara, caja, polígonos píxel, porcentaje del área de imagen, CSV, JSON, GeoJSON, PNG y ZIP.
- Video procesado fotograma a fotograma, tracking temporal con ByteTrack, IDs de seguimiento, MP4 H.264 si FFmpeg está instalado, CSV y ZIP. `frame_step` controla muestreo; frames no evaluados permanecen originales. Los IDs pueden fragmentarse y no constituyen número certificado de baches únicos.
- Comparador de cuatro modelos con previsualización, latencia, detecciones y confianza promedio. Esas medidas no prueban exactitud relativa.
- Benchmark *real* con dataset anotado YOLO: colocar archivos dentro de `datasets/`, enviar ruta YAML relativa en pestaña Benchmark. Por ejemplo `mi_dataset/data.yaml` y utilizar `val` o `test`. Incluye mAP de cajas y máscaras. Solo usar datasets confiables.
- Historial SQLite persistente, API REST con clave opcional, mapa GPS si se aportan coordenadas, exportación y controles de tamaño/formato.
- Selección automática CUDA/CPU. Para CUDA instalar versiones PyTorch compatibles con su GPU y drivers.

## API

- `GET /api/health`, `/api/models`, `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/result`
- `POST /api/analyze` (multipart: file, model, conf, iou, imgsz, alpha, boxes, masks, frame_step, max_frames, lat, lon)
- `POST /api/compare` (imagen, conf, iou, imgsz)
- `POST /api/benchmark` (dataset_yaml, split, imgsz)
- `GET /api/jobs/{id}/file/{filename}`, `/api/jobs/{id}/export.zip`

## Limitaciones y preparación para producción

- SQLite y threads daemon son adecuados para un **único proceso / instancia**, no una cola distribuida con garantía de recuperación: para AWS multiusuario migrar a PostgreSQL/PostGIS, almacenamiento S3 y workers Redis/Celery, añadir cuotas, autenticación individual, auditoría y monitoreo. No ejecutar Uvicorn con múltiples workers usando esta cola local.
- El video puede no tener sonido: la salida se renderiza desde fotogramas OpenCV. Se impone un límite de 18 000 fotogramas, configuración máxima de 400 MB por carga y 40 MP por imagen. Ajustar según infraestructura.
- Coordenadas lat/lon representan el GPS suministrado para el archivo. No se infieren posiciones por bache ni dimensiones métricas. GeoJSON sin GPS contiene geometría null con polígonos en píxeles como propiedades.
- No se atribuye automáticamente gravedad física por área 2D: requiere calibración/medición de profundidad e inspección profesional.
- En la variante actual se incluye historial básico y no una aplicación corporativa de gestión de órdenes de reparación. Se puede ampliar con esquema PostgreSQL, GIS y flujos de usuarios.

## Pruebas

`pytest -q` (pruebas de API/validación que no requieren inferencia). Probar separadamente predicción de cada checkpoint en el entorno final con imágenes etiquetadas.

## Estructura

`backend/` API, inferencia, seguimiento y base de datos; `frontend/` interfaz; `models/` checkpoints originales; `data/` resultados persistentes; `datasets/` validación; `tests/` pruebas; `Dockerfile`, `docker-compose.yml`.

## V2.1: Severidad visual y GPS
- En Analizar, ajusta límites de **cobertura segmentada de la imagen** (por defecto 0,5% y 2,5%). Salidas: `baja`, `media`, `alta` y `sin_mascara`, además de un resumen en JSON/CSV. Estas etiquetas son **heurísticas de ocupación visual sin validación clínica/ingenieril**: no infieren profundidad, medidas métricas ni peligro. La perspectiva, distancia, zoom y resolución alteran estos valores. Para evaluación vial real, incorporar referencia de escala, cámara calibrada o sensor de profundidad y validación por personal técnico. En video el resumen cuenta observaciones por fotograma, no baches únicos.
- Pulsa **Usar mi ubicación actual** y acepta permiso de ubicación del navegador. Requiere **HTTPS** (despliegue remoto) o `http://localhost:8000` / `http://127.0.0.1:8000` en el dispositivo que capture la ubicación. Activa Ubicación/GPS en tu sistema y permisos de sitio en el navegador. También puedes introducir latitud y longitud manualmente. La coordenada se asocia al archivo completo y aparece en el mapa/GeoJSON: **no** es la posición GPS individual de cada bache. Para video móvil en movimiento se requerirá trayectoria GPX sincronizada y calibración/correlación temporal.
- Nunca publiques sin protección de autenticación, control de acceso y política de privacidad de ubicación. `BACHES_API_KEY` es protección básica; reforzarla en producción.

### Próximas mejoras prioritarias
1. Dataset de campo etiquetado y benchmark real de los cuatro checkpoints; verificar compatibilidad y calidad de máscaras.
2. Deduplificación espacial/temporal de baches y trazas GPX para videos en movimiento.
3. Calibración geométrica/profundidad y protocolo vial para severidad estructural.
4. Autenticación por usuario, privacidad GPS, almacenamiento externo, PostgreSQL/PostGIS y colas Celery/Redis; limitar concurrencia y proteger endpoints de archivos.
5. Pruebas de integración con modelos reales y videos, observabilidad, copias de seguridad, despliegue HTTPS.
