"""
Tests del motor de cálculo — Validados contra datos reales del Excel PRECIOS_EJEMPLO_2025.
"""
import pytest
from app.engine.pricing_engine import (
    calcular_precio_tratamiento,
    calcular_descuentos,
    generar_dashboard_ganancias,
)


class MockConfig:
    def __init__(self, gastos_fijos=50000, horas_semana=46, numero_unidades=2):
        self.gastos_fijos = gastos_fijos
        self._horas_semana = horas_semana
        self.numero_unidades = numero_unidades

    @property
    def horas_semana(self):
        return self._horas_semana

    @property
    def horas_mes(self):
        return self._horas_semana * 4

    @property
    def costo_hora(self):
        if self.horas_mes > 0 and self.numero_unidades > 0:
            return self.gastos_fijos / self.horas_mes / self.numero_unidades
        return 0


class MockMaterial:
    def __init__(self, id, nombre, costo_paquete, unidades_paquete):
        self.id = id
        self.nombre = nombre
        self.costo_paquete = costo_paquete
        self.unidades_paquete = unidades_paquete

    @property
    def costo_unitario(self):
        return self.costo_paquete / self.unidades_paquete if self.unidades_paquete > 0 else 0


class MockTratamientoMaterial:
    def __init__(self, material, cantidad):
        self.material = material
        self.cantidad = cantidad


class MockTratamiento:
    def __init__(self, id, nombre, horas, precio, com_bancaria_pct, com_esp_tipo, com_esp_valor):
        self.id = id
        self.nombre = nombre
        self.horas_invertidas = horas
        self.precio_paciente = precio
        self.comision_bancaria_pct = com_bancaria_pct
        self.comision_especialista_tipo = com_esp_tipo
        self.comision_especialista_valor = com_esp_valor


class TestPricingEngine:
    """Test con datos del Excel: config gastos_fijos=50000, horas=46/sem, unidades=2."""

    def setup_method(self):
        self.config = MockConfig(gastos_fijos=50000, horas_semana=46, numero_unidades=2)
        # costo_hora = 50000 / (46*4) / 2 = 50000 / 184 / 2 = 135.87

    def test_costo_hora(self):
        assert round(self.config.costo_hora, 2) == 135.87

    def test_resina_c2(self):
        """RESINA_C2: horas=1, precio=1200, com_bancaria=5%, com_esp=35% porcentaje"""
        materiales = [
            MockTratamientoMaterial(MockMaterial(1, "DIQUE HULE", 290, 36), 1),
            MockTratamientoMaterial(MockMaterial(2, "AGUJAS ANESTESIA", 166, 100), 1),
            MockTratamientoMaterial(MockMaterial(3, "TOPICAINA GEL", 80, 150), 1),
            MockTratamientoMaterial(MockMaterial(4, "CAMPOS DE COLORES", 100, 25), 1),
            MockTratamientoMaterial(MockMaterial(5, "BABERO DESECHABLE", 50, 50), 1),
            MockTratamientoMaterial(MockMaterial(6, "CUBREBOCAS", 100, 50), 2),
            MockTratamientoMaterial(MockMaterial(7, "ACIDO GRABRADOR ULTRADENT", 250, 90), 2),
            MockTratamientoMaterial(MockMaterial(8, "RESINA FLUIDA", 300, 20), 1),
            MockTratamientoMaterial(MockMaterial(9, "GASAS", 50, 150), 3),
            MockTratamientoMaterial(MockMaterial(10, "GUANTES DE LATEX", 170, 50), 2),
            MockTratamientoMaterial(MockMaterial(11, "ANESTESIA LIDOCAINA 2% CON EPINEFRINA", 500, 100), 1),
        ]

        tx = MockTratamiento(
            id=1, nombre="RESINA_C2", horas=1, precio=1200,
            com_bancaria_pct=5, com_esp_tipo="porcentaje", com_esp_valor=35,
        )

        result = calcular_precio_tratamiento(self.config, tx, materiales)

        assert result["costo_hora_consultorio"] == 135.87
        assert result["costo_consultorio_tx"] == 135.87
        assert result["comision_bancaria"] == 60.0
        assert result["comision_especialista"] == 420.0
        assert result["costo_materiales"] > 0
        assert result["costo_tratamiento"] > 0
        assert result["ganancia_neta"] == round(1200 - result["costo_tratamiento"], 2)
        assert len(result["descuentos"]) == 4

    def test_cx_3ros_costo_fijo(self):
        """CX_DE_3ROS_M: com_especialista tipo 'fijo' = $1500"""
        tx = MockTratamiento(
            id=2, nombre="CX_DE_3ROS_M", horas=0.5, precio=3500,
            com_bancaria_pct=5, com_esp_tipo="fijo", com_esp_valor=1500,
        )
        result = calcular_precio_tratamiento(self.config, tx, [])

        assert result["comision_especialista"] == 1500.0
        assert result["comision_bancaria"] == 175.0
        assert result["costo_consultorio_tx"] == round(0.5 * self.config.costo_hora, 2)

    def test_descuentos(self):
        result = calcular_descuentos(500, 1200)
        assert len(result) == 4
        assert result[0]["porcentaje"] == 10
        assert result[0]["monto_descuento"] == 120.0
        assert result[0]["precio_con_descuento"] == 1080.0
        assert result[0]["ganancia"] == 580.0

    def test_precio_minimo(self):
        tx = MockTratamiento(
            id=3, nombre="TEST", horas=1, precio=1000,
            com_bancaria_pct=0, com_esp_tipo="fijo", com_esp_valor=0,
        )
        result = calcular_precio_tratamiento(self.config, tx, [])
        # precio_minimo = costo_tratamiento / 0.7
        expected_min = round(result["costo_tratamiento"] / 0.7, 2)
        assert result["precio_minimo_sugerido"] == expected_min

    def test_dashboard_ganancias(self):
        tx1 = MockTratamiento(1, "TX1", 1, 1000, 5, "porcentaje", 30, )
        tx2 = MockTratamiento(2, "TX2", 0.5, 2000, 5, "fijo", 500)

        result = generar_dashboard_ganancias(
            self.config,
            [(tx1, []), (tx2, [])],
            [0, 0.20, 0.30],
        )

        assert result["totales"]["total_tratamientos"] == 2
        assert len(result["resumen"]) == 2
        assert len(result["resumen"][0]["escenarios_comision"]) == 3


class TestEdgeCases:
    def test_zero_price(self):
        config = MockConfig()
        tx = MockTratamiento(1, "FREE", 1, 0, 5, "porcentaje", 35)
        result = calcular_precio_tratamiento(config, tx, [])
        assert result["pct_ganancia"] == 0

    def test_zero_hours(self):
        config = MockConfig(horas_semana=0)
        tx = MockTratamiento(1, "TEST", 1, 1000, 0, "fijo", 0)
        result = calcular_precio_tratamiento(config, tx, [])
        assert result["costo_hora_consultorio"] == 0
        assert result["costo_consultorio_tx"] == 0
