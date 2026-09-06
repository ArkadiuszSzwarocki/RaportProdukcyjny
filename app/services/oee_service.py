from typing import Dict, Any, Optional
from datetime import datetime, date
from app.repositories.oee_repository import OeeRepository

class OeeService:
    """
    Domain service for real-time Overall Equipment Effectiveness (OEE) calculation.
    OEE = Availability (Dostępność) x Performance (Wydajność) x Quality (Jakość)
    """

    DEFAULT_PLANNED_SHIFT_MINUTES = 480  # 8-hour shift standard

    @staticmethod
    def calculate_realtime_oee(
        target_date: Optional[str] = None,
        linia: str = 'PSD',
        planned_shift_minutes: int = DEFAULT_PLANNED_SHIFT_MINUTES
    ) -> Dict[str, Any]:
        """
        Calculates Availability, Performance, Quality, and overall OEE percentage.
        """
        if not target_date:
            target_date = datetime.now().strftime('%Y-%m-%d')

        norm_line = str(linia or 'PSD').upper()
        
        # 1. Production data
        prod_data = OeeRepository.get_shift_production_data(target_date, norm_line)
        planned_tonnage = prod_data.get('planned_tonnage', 0.0)
        actual_tonnage = prod_data.get('actual_tonnage', 0.0)

        # 2. Downtime data
        downtime_minutes = OeeRepository.get_shift_downtime_minutes(target_date, norm_line)

        # 3. Quality loss
        quality_loss_kg = OeeRepository.get_shift_quality_losses_kg(target_date, norm_line)
        quality_loss_tonnage = quality_loss_kg / 1000.0

        # --- A. AVAILABILITY (Dostępność) ---
        # Operating Time / Planned Production Time
        operating_minutes = max(0, planned_shift_minutes - downtime_minutes)
        availability_pct = round((operating_minutes / planned_shift_minutes) * 100.0, 2) if planned_shift_minutes > 0 else 100.0
        availability_pct = min(100.0, max(0.0, availability_pct))

        # --- B. PERFORMANCE (Wydajność) ---
        # Actual Output / Target Output
        if planned_tonnage > 0:
            performance_pct = round((actual_tonnage / planned_tonnage) * 100.0, 2)
        else:
            performance_pct = 100.0 if actual_tonnage > 0 else 0.0
        performance_pct = min(120.0, max(0.0, performance_pct))  # cap slightly above 100% for overperformance

        # --- C. QUALITY (Jakość) ---
        # Good Output / Total Actual Output
        if actual_tonnage > 0:
            good_tonnage = max(0.0, actual_tonnage - quality_loss_tonnage)
            quality_pct = round((good_tonnage / actual_tonnage) * 100.0, 2)
        else:
            quality_pct = 100.0
        quality_pct = min(100.0, max(0.0, quality_pct))

        # --- D. OVERALL OEE ---
        oee_factor = (availability_pct / 100.0) * (performance_pct / 100.0) * (quality_pct / 100.0)
        overall_oee_pct = round(oee_factor * 100.0, 2)

        return {
            "date": target_date,
            "linia": norm_line,
            "oee_percent": overall_oee_pct,
            "availability": {
                "percent": availability_pct,
                "planned_minutes": planned_shift_minutes,
                "downtime_minutes": downtime_minutes,
                "operating_minutes": operating_minutes
            },
            "performance": {
                "percent": performance_pct,
                "planned_tonnage": round(planned_tonnage, 2),
                "actual_tonnage": round(actual_tonnage, 2),
                "completed_orders": prod_data.get('completed_orders', 0)
            },
            "quality": {
                "percent": quality_pct,
                "quality_loss_kg": round(quality_loss_kg, 2),
                "good_tonnage": round(max(0.0, actual_tonnage - quality_loss_tonnage), 2)
            }
        }
