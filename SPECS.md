# ⚙️ Backend Technical Specifications — Residuos_CLARA_Back

> **Proyecto**: API REST & Backend Engine para Clasificación y Declaración de RESPEL (ULima)  
> **Framework**: Python 3.14 / FastAPI + SQLAlchemy / PostgreSQL + openpyxl + Gemini API  

---

## 🏛️ 1. Módulos y Arquitectura Backend

1. **Motor Determinista de Clasificación (`core/classifier.py`)**:
   - Ejecuta la Ontología Canónica ULima v2 (15 categorías).
   - Valida la Matriz de Incompatibilidad CSBQR (11×11) con regla de "segregar por defecto".
   - Mapea a las 7 clases oficiales de declaración SUNAT/MINAM.

2. **Generador de Excel Oficial (`core/excel_generator.py`)**:
   - Plantilla `Formato-Declaración de residuos peligrosos generados-2026.xlsx`.
   - Relleno de Hoja 1 (`DB_Registros`) y Hoja 2 (`DB_Residuos`) con fotos insertadas.
   - Solución a enlaces de Google Drive `/file/d/<id>/view` y conversión float para comas.

3. **Integración con Gemini RAG (`core/gemini_service.py`)**:
   - Generación de la narrativa *"Sobre este residuo"*.
   - Extracción de peligrosidad de Hojas de Seguridad (SDS/FDS) subidas en PDF/imagen.

---

## 🔌 2. Endpoints API REST

- `POST /api/v1/clasificar`: Entrada de residuo $\rightarrow$ Resultado con confianza, incompatibilidad y etiqueta.
- `POST /api/v1/acopio/verificar`: Array de IDs de residuo $\rightarrow$ Veredicto (Compatibles / Segregar / NUNCA).
- `POST /api/v1/exportar/declaracion`: ID de registro $\rightarrow$ Stream de archivo Excel oficial 2026/v3.
- `POST /api/v1/exportar/traslado`: ID de registro $\rightarrow$ Stream de archivo Excel de traslado interno.
- `GET /api/v1/etiqueta/{id}/pdf`: ID de residuo $\rightarrow$ PDF renderizado 10×15 cm con QR y GHS.
- `POST /api/v1/historico/benchmark`: Ejecuta el motor contra los 856 residuos históricos reales.
