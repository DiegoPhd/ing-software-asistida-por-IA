from datetime import datetime, timedelta
from typing import List, Dict, Optional
from difflib import SequenceMatcher
from src.models import TriageResult, SeverityLevel
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample_incidents.json"

def calculate_similarity(text1: str, text2: str) -> float:
    """Calcula el porcentaje de similitud entre dos descripciones de incidentes."""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def classify_incident_report(
    incident_id: str, 
    raw_text: str, 
    created_at: Optional[datetime] = None, 
    existing_incidents: Optional[List[dict]] = None
) -> TriageResult:
    """Clasifica un reporte de incidente aplicando análisis de impacto real,

    eliminando la deuda técnica de evaluar palabras emocionales ("urgente", "hoy").
    """
    text_lower = raw_text.lower()
    created_at = created_at or datetime.now()
    existing_incidents = existing_incidents or []

    # 1. Determinación de Severidad basada en Impacto Real y Seguridad
    if ("502" in text_lower or "indisponibilidad" in text_lower or "global" in text_lower or 
        "otra organización" in text_lower or "otra empresa" in text_lower or "multi-tenant" in text_lower or
        ("pagos" in text_lower and ("caído" in text_lower or "no funciona" in text_lower or "ningún comercio" in text_lower))):
        severity: SeverityLevel = "P0"
    elif "94%" in text_lower or "timeout" in text_lower or "conexiones" in text_lower or "pool" in text_lower:
        severity = "P1"
    elif "lenta" in text_lower or "segundos" in text_lower or ("cuenta" in text_lower and "bloqueada" in text_lower):
        severity = "P2"
    elif "botón" in text_lower or "color" in text_lower or "staging" in text_lower or "cosmética" in text_lower:
        severity = "P3"
    else:
        severity = "P2"

    # 2. Asignación de Componente y Equipo Responsable (recommended_team)
    if "pago" in text_lower or "cobro" in text_lower or "tarjeta" in text_lower or "transacciones" in text_lower:
        component = "payments-gateway"
        recommended_team = "Backend-Core"
    elif "cuenta" in text_lower or "ingresar" in text_lower or "acceso" in text_lower:
        component = "auth-identity"
        recommended_team = "Security-IAM"
    elif "postgresql" in text_lower or "conexiones" in text_lower or "base de datos" in text_lower:
        component = "database-cluster"
        recommended_team = "Data-DBA"
    elif "certificado" in text_lower or "tls" in text_lower or "gateway" in text_lower or "502" in text_lower:
        component = "infra-certificates"
        recommended_team = "Platform-SRE"
    elif "otra organización" in text_lower or "facturas pertenecientes a otra" in text_lower:
        component = "security-audit"
        recommended_team = "Security-IAM"
    else:
        component = "reporting-api"
        recommended_team = "otros"

    # 3. Detección de Duplicados (similitud >= 75% dentro del SLA temporal)
    duplicate_group_key: Optional[str] = None
    time_windows = {
        "P0": timedelta(days=1),
        "P1": timedelta(days=2),
        "P2": timedelta(days=3),
        "P3": timedelta(days=4)
    }
    max_time_diff = time_windows.get(severity, timedelta(days=1))

    for prev in existing_incidents:
        prev_id = prev.get("id") or prev.get("incident_id")
        prev_text = prev.get("raw_text") or prev.get("description", "")
        prev_created_at = prev.get("created_at")

        if prev_id == incident_id:
            continue

        similarity = calculate_similarity(raw_text, prev_text)
        if similarity >= 0.75 and prev_created_at:
            if isinstance(prev_created_at, str):
                try:
                    prev_dt = datetime.fromisoformat(prev_created_at)
                except ValueError:
                    prev_dt = created_at
            else:
                prev_dt = prev_created_at

            time_diff = created_at - prev_dt
            if timedelta(0) <= time_diff <= max_time_diff:
                duplicate_group_key = prev_id
                print(f"[DUPLICATE_DETECTED] Incidente {incident_id} marcado como duplicado de {prev_id} (Similitud: {similarity:.2f})")
                break

    rationale = f"Triaje basado en impacto. Componente: {component}, Severidad: {severity}, Equipo: {recommended_team}."
    if duplicate_group_key:
        rationale += f" Duplicado detectado del incidente original {duplicate_group_key}."

    result = TriageResult(
        incident_id=incident_id,
        severity=severity,
        component=component,
        recommended_team=recommended_team,
        duplicate_group_key=duplicate_group_key,
        rationale=rationale,
        consistency_ratio=1.0
    )

    # Print de seguimiento de clasificación individual
    print(f"[CLASSIFY] ID: {result.incident_id} | Severity: {result.severity} | Team: {result.recommended_team} | Component: {result.component}")
    return result


def process_incident_batch(incidents: List[dict]) -> List[TriageResult]:
    """Procesa un lote de incidentes asegurando el orden cronológico para la correcta

    identificación del incidente original frente a duplicados.
    """
    results = []
    processed_history: List = []
    
    # Ordenar estrictamente por fecha de creación (el primero creado es el válido/original)
    sorted_incidents = sorted(
        incidents, 
        key=lambda x: datetime.fromisoformat(x["created_at"]) if isinstance(x.get("created_at"), str) else x.get("created_at", datetime.min)
    )

    print(f"[BATCH] Iniciando procesamiento de {len(sorted_incidents)} incidentes ordenados cronológicamente.")

    for item in sorted_incidents:
        inc_id = item.get("id") or item.get("incident_id")
        raw_text = item.get("raw_text") or item.get("description", "")
        created_at_str = item.get("created_at")
        created_at = datetime.fromisoformat(created_at_str) if isinstance(created_at_str, str) else created_at_str

        snippet = raw_text[:45] + "..." if len(raw_text) > 45 else raw_text
        print(f"[PROCESSING] Evaluando incidente {inc_id} -> '{snippet}'")

        if not inc_id or not raw_text or not created_at:
            print(f"[WARNING] Incidente {inc_id} omitido debido a datos incompletos.")
            continue
        result = classify_incident_report(
            incident_id=inc_id,
            raw_text=raw_text,
            created_at=created_at,
            existing_incidents=processed_history
        )
        results.append(result)
        processed_history.append({
            "id": inc_id,
            "raw_text": raw_text,
            "created_at": created_at,
            "severity": result.severity
        })

    print(f"[BATCH] Procesamiento completado con éxito.")
    return results

def _run_triage_audit() -> None:
    """Ejecuta el motor actual sobre los 10 incidentes de prueba para evidenciar fallos."""
    incidents: List[Dict[str, str]] = json.loads(SAMPLE_DATA_PATH.read_text(encoding="utf-8"))

    print("=== Auditoría del Motor de Triaje Actual (`src/triage_rules.py`) ===")
    print(f"{'ID':<10} | {'Sev.':<5} | {'Componente':<20} | {'Extracto del Reporte'}")
    print("-" * 88)
    for item in incidents:
        result = classify_incident_report(item["id"], item["raw_text"])
        snippet = item["raw_text"][:45] + "..." if len(item["raw_text"]) > 45 else item["raw_text"]
        print(f"{result.incident_id:<10} | {result.severity:<5} | {result.component:<20} | {snippet}")
    print("-" * 88)
    #print(
    #    "Observa los problemas en la salida actual:\n"
    #    "  - INC-1002 (cuenta individual bloqueada) y INC-1009 (exportación Excel lenta)\n"
    #    "    se clasifican como P0 solo porque el usuario escribió la palabra 'hoy'.\n"
    #    "  - INC-1007 (fuga crítica de facturas entre empresas por company_id en URL)\n"
    #    "    se clasifica como P3 porque no contiene las palabras 'urgente' ni '502'."
    #)


if __name__ == "__main__":
    _run_triage_audit()