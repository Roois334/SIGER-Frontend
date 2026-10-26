"""Informe PDF de estadisticas de SIGER (HU-17), generado con reportlab."""
import io
import math
import os

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT

LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "img", "siger-redondo.png")

NAVY = HexColor("#0B1424")
NAVY2 = HexColor("#12294A")
AZUL = HexColor("#1E88E5")
AZUL_CL = HexColor("#64B5F6")
TEXTO = HexColor("#1B2A41")
GRIS = HexColor("#6B7C93")
BORDE = HexColor("#DCE6F2")
FONDO = HexColor("#F4F8FD")
VERDE = HexColor("#00A854")
ROJO = HexColor("#E5484D")
AMBAR = HexColor("#F5A524")
NARANJA = HexColor("#FB8C00")
MORADO = HexColor("#AB47BC")
PIZARRA = HexColor("#6B7C93")
TURQ = HexColor("#00ACC1")

COLOR_ESTADO = {"pendiente": AMBAR, "asignado": AZUL, "en_atencion": MORADO,
                "resuelto": VERDE, "cerrado": PIZARRA, "descartado": ROJO}
COLOR_PRIO = {"critica": ROJO, "alta": NARANJA, "media": AZUL, "baja": VERDE}

MARGEN = 16 * mm
ANCHO, ALTO = A4
UTIL = ANCHO - 2 * MARGEN
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _num(n):
    return f"{int(n):,}".replace(",", ".")


def _pct(p):
    return f"{p:.1f}".replace(".", ",") + "%"


def _recortar(txt, fuente, tam, ancho):
    txt = str(txt)
    if stringWidth(txt, fuente, tam) <= ancho:
        return txt
    while txt and stringWidth(txt + "...", fuente, tam) > ancho:
        txt = txt[:-1]
    return txt.rstrip() + "..."


def _etq(e, gran, largo=False):
    a, m, *d = e.split("-")
    if gran == "mes":
        return f"{MESES[int(m) - 1]} {a}" if largo else MESES[int(m) - 1] + (f" {a[2:]}" if m == "01" else "")
    return f"{int(d[0])} {MESES[int(m) - 1]}"


# ----------------------------------------------------------------- flowables
class Titulo(Flowable):
    def __init__(self, texto, nota=""):
        super().__init__(); self.texto, self.nota = texto, nota
    def wrap(self, w, h):
        self.w = w; return w, 9 * mm
    def draw(self):
        c = self.canv
        c.setFillColor(AZUL); c.roundRect(0, 1.2 * mm, 1.6 * mm, 5.2 * mm, 0.8 * mm, stroke=0, fill=1)
        c.setFillColor(TEXTO); c.setFont("Helvetica-Bold", 12); c.drawString(4 * mm, 2.2 * mm, self.texto)
        if self.nota:
            c.setFillColor(GRIS); c.setFont("Helvetica", 8); c.drawRightString(self.w, 2.4 * mm, self.nota)


class Kpis(Flowable):
    """Tarjetas de indicadores en cuadricula de 3 columnas."""
    def __init__(self, items):
        super().__init__(); self.items = items
    def wrap(self, w, h):
        self.w = w; filas = math.ceil(len(self.items) / 3); self.alto = filas * 27 * mm + (filas - 1) * 4 * mm
        return w, self.alto
    def draw(self):
        c = self.canv; gap = 4 * mm; cw = (self.w - 2 * gap) / 3; ch = 27 * mm
        for i, (etq, valor, nota, color) in enumerate(self.items):
            f, col = divmod(i, 3)
            x = col * (cw + gap); y = self.alto - (f + 1) * ch - f * gap
            c.setFillColor(FONDO); c.setStrokeColor(BORDE); c.setLineWidth(0.7)
            c.roundRect(x, y, cw, ch, 3 * mm, stroke=1, fill=1)
            c.saveState(); p = c.beginPath(); p.roundRect(x, y, cw, ch, 3 * mm); c.clipPath(p, stroke=0, fill=0)
            c.setFillColor(color); c.rect(x, y + ch - 1.6 * mm, cw, 1.6 * mm, stroke=0, fill=1); c.restoreState()
            c.setFillColor(GRIS); c.setFont("Helvetica-Bold", 7); c.drawString(x + 4 * mm, y + ch - 7.2 * mm, _recortar(etq.upper(), "Helvetica-Bold", 7, cw - 8 * mm))
            c.setFillColor(TEXTO); c.setFont("Helvetica-Bold", 20); c.drawString(x + 4 * mm, y + ch - 16 * mm, valor)
            c.setFillColor(GRIS); c.setFont("Helvetica", 7.4); c.drawString(x + 4 * mm, y + 4.2 * mm, _recortar(nota, "Helvetica", 7.4, cw - 8 * mm))


class Area(Flowable):
    def __init__(self, serie):
        super().__init__(); self.s = serie
    def wrap(self, w, h):
        self.w = w; return w, 54 * mm
    def draw(self):
        c = self.canv; pts = self.s["puntos"]; gran = self.s["granularidad"]; W, H = self.w, 54 * mm
        ml, mb, mt, mr = 9 * mm, 8 * mm, 3 * mm, 2 * mm
        iw, ih = W - ml - mr, H - mb - mt
        c.setFillColor(white); c.setStrokeColor(BORDE); c.roundRect(0, 0, W, H, 3 * mm, stroke=1, fill=1)
        if not pts:
            c.setFillColor(GRIS); c.setFont("Helvetica", 9); c.drawCentredString(W / 2, H / 2, "Sin datos para mostrar"); return
        mx = max(max(p["total"] for p in pts), 1)
        paso = next((p for p in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000) if mx / p <= 5), 1000)
        tope = math.ceil(mx / paso) * paso
        n = len(pts)
        X = lambda i: ml + (iw / 2 if n == 1 else i / (n - 1) * iw)
        Y = lambda v: mb + v / tope * ih
        c.setFont("Helvetica", 7); c.setLineWidth(0.4)
        v = 0
        while v <= tope:
            c.setStrokeColor(BORDE); c.line(ml, Y(v), ml + iw, Y(v))
            c.setFillColor(GRIS); c.drawRightString(ml - 2 * mm, Y(v) - 2.4, str(v)); v += paso
        cada = max(1, math.ceil(n / 8))
        for i, p in enumerate(pts):
            if i % cada == 0:
                c.setFillColor(GRIS); c.drawCentredString(X(i), 2.6 * mm, _etq(p["etiqueta"], gran))
        c.saveState(); path = c.beginPath(); path.moveTo(X(0), Y(0))
        for i, p in enumerate(pts): path.lineTo(X(i), Y(p["total"]))
        path.lineTo(X(n - 1), Y(0)); path.close()
        c.setFillColor(AZUL); c.setFillAlpha(0.16); c.drawPath(path, stroke=0, fill=1); c.restoreState()
        c.setStrokeColor(AZUL); c.setLineWidth(1.4 if n < 45 else 1.0); c.setLineJoin(1)
        lp = c.beginPath(); lp.moveTo(X(0), Y(pts[0]["total"]))
        for i, p in enumerate(pts[1:], 1): lp.lineTo(X(i), Y(p["total"]))
        c.drawPath(lp, stroke=1, fill=0)
        if n <= 31:
            c.setFillColor(white); c.setLineWidth(1)
            for i, p in enumerate(pts): c.circle(X(i), Y(p["total"]), 1.1 * mm, stroke=1, fill=1)


class Barras(Flowable):
    def __init__(self, filas, color, nombre=lambda x: x, ancho_nombre=0.34):
        super().__init__(); self.filas, self.color, self.nombre, self.an = filas, color, nombre, ancho_nombre
    def wrap(self, w, h):
        self.w = w; self.alto = max(len(self.filas), 1) * 8 * mm; return w, self.alto
    def draw(self):
        c = self.canv; filas = self.filas
        if not filas:
            c.setFillColor(GRIS); c.setFont("Helvetica", 9); c.drawString(0, self.alto - 6 * mm, "Sin datos para mostrar"); return
        mx = max(max(f["total"] for f in filas), 1); nw = self.w * self.an; vw = 24 * mm; bw = self.w - nw - vw - 6 * mm
        for i, f in enumerate(filas):
            y = self.alto - (i + 1) * 8 * mm
            col = self.color(f["clave"]) if callable(self.color) else self.color
            c.setFillColor(TEXTO); c.setFont("Helvetica", 8.6)
            c.drawString(0, y + 2.6 * mm, _recortar(self.nombre(f["clave"]), "Helvetica", 8.6, nw - 2 * mm))
            c.setFillColor(HexColor("#E8EFF8")); c.roundRect(nw, y + 2.2 * mm, bw, 3 * mm, 1.5 * mm, stroke=0, fill=1)
            ancho = max(bw * f["total"] / mx, 3 * mm if f["total"] else 0)
            if ancho: c.setFillColor(col); c.roundRect(nw, y + 2.2 * mm, ancho, 3 * mm, 1.5 * mm, stroke=0, fill=1)
            c.setFillColor(TEXTO); c.setFont("Helvetica-Bold", 8.6); c.drawRightString(self.w - 11.5 * mm, y + 2.6 * mm, _num(f["total"]))
            c.setFillColor(GRIS); c.setFont("Helvetica", 7.6); c.drawRightString(self.w, y + 2.6 * mm, _pct(f["porcentaje"]))


class Dona(Flowable):
    def __init__(self, filas, colores, nombre):
        super().__init__(); self.filas, self.colores, self.nombre = filas, colores, nombre
    def wrap(self, w, h):
        self.w = w; return w, 40 * mm
    def draw(self):
        c = self.canv; filas = self.filas; total = sum(f["total"] for f in filas); d = 30 * mm; cx, cy = d / 2 + 1 * mm, 20 * mm
        if not total:
            c.setFillColor(GRIS); c.setFont("Helvetica", 9); c.drawString(0, 20 * mm, "Sin datos para mostrar"); return
        ang = 90.0
        for f in filas:
            if not f["total"]: continue
            ext = -360.0 * f["total"] / total
            c.setFillColor(self.colores.get(f["clave"], AZUL)); c.setStrokeColor(white); c.setLineWidth(1.2)
            c.wedge(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2, ang, ext, stroke=1, fill=1); ang += ext
        c.setFillColor(white); c.circle(cx, cy, d * 0.31, stroke=0, fill=1)
        c.setFillColor(TEXTO); c.setFont("Helvetica-Bold", 15); c.drawCentredString(cx, cy - 1, _num(total))
        c.setFillColor(GRIS); c.setFont("Helvetica", 5.6); c.drawCentredString(cx, cy - 7.5, "EMERGENCIAS")
        lx = d + 5 * mm; y = 20 * mm + len(filas) * 5.6 * mm / 2 - 4 * mm
        for f in filas:
            c.setFillColor(self.colores.get(f["clave"], AZUL)); c.roundRect(lx, y - 0.6 * mm, 2.8 * mm, 2.8 * mm, 0.8 * mm, stroke=0, fill=1)
            c.setFillColor(TEXTO); c.setFont("Helvetica", 8.2); c.drawString(lx + 4.6 * mm, y, _recortar(self.nombre(f["clave"]), "Helvetica", 8.2, 19 * mm))
            c.setFont("Helvetica-Bold", 8.2); c.drawRightString(self.w - 11 * mm, y, _num(f["total"]))
            c.setFillColor(GRIS); c.setFont("Helvetica", 7.2); c.drawRightString(self.w, y, _pct(f["porcentaje"])); y -= 5.6 * mm


# ----------------------------------------------------------------- pagina
class _Numerado(rl_canvas.Canvas):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self._paginas = []
    def showPage(self):
        self._paginas.append(dict(self.__dict__)); self._startPage()
    def save(self):
        total = len(self._paginas)
        for est in self._paginas:
            self.__dict__.update(est); self._pie(total); super().showPage()
        super().save()
    def _pie(self, total):
        self.setStrokeColor(BORDE); self.setLineWidth(0.6); self.line(MARGEN, 14 * mm, ANCHO - MARGEN, 14 * mm)
        self.setFillColor(GRIS); self.setFont("Helvetica", 7.5)
        self.drawString(MARGEN, 9.5 * mm, "SIGER · Sistema de Gestión de Emergencias Regional · Sabana de Occidente")
        self.drawRightString(ANCHO - MARGEN, 9.5 * mm, f"Página {self._pageNumber} de {total}")


def _portada(c, doc, info):
    h = 44 * mm
    c.saveState()
    c.setFillColor(NAVY); c.rect(0, ALTO - h, ANCHO, h, stroke=0, fill=1)
    c.saveState(); rec = c.beginPath(); rec.rect(0, ALTO - h, ANCHO, h); c.clipPath(rec, stroke=0, fill=0)
    c.setFillColor(NAVY2); c.setFillAlpha(0.55); c.circle(ANCHO - 12 * mm, ALTO - 4 * mm, 46 * mm, stroke=0, fill=1)
    c.setFillAlpha(0.2); c.setFillColor(AZUL); c.circle(ANCHO - 1 * mm, ALTO - 40 * mm, 17 * mm, stroke=0, fill=1); c.setFillAlpha(1); c.restoreState()
    c.setFillColor(AZUL); c.rect(0, ALTO - h - 1.4 * mm, ANCHO * 0.55, 1.4 * mm, stroke=0, fill=1)
    c.setFillColor(AZUL_CL); c.rect(ANCHO * 0.55, ALTO - h - 1.4 * mm, ANCHO * 0.45, 1.4 * mm, stroke=0, fill=1)
    d = 27 * mm
    c.setFillColor(HexColor("#1B3A5F")); c.circle(MARGEN + d / 2, ALTO - h / 2, d / 2 + 1.2 * mm, stroke=0, fill=1)
    if os.path.exists(LOGO):
        c.drawImage(LOGO, MARGEN, ALTO - h / 2 - d / 2, d, d, mask="auto")
    x = MARGEN + d + 7 * mm
    c.setFillColor(white); c.setFont("Helvetica-Bold", 25); c.drawString(x, ALTO - h / 2 + 2.5 * mm, "SIGER")
    c.setFillColor(AZUL_CL); c.setFont("Helvetica", 9.2); c.drawString(x, ALTO - h / 2 - 3.8 * mm, "Sistema de Gestión de Emergencias Regional")
    c.setFillColor(HexColor("#8FA8C9")); c.setFont("Helvetica", 8.2); c.drawString(x, ALTO - h / 2 - 9 * mm, "Sabana de Occidente")
    c.setFillColor(white); c.setFont("Helvetica-Bold", 10.5); c.drawRightString(ANCHO - MARGEN, ALTO - h / 2 + 3.5 * mm, "INFORME DE ESTADÍSTICAS")
    c.setFillColor(HexColor("#8FA8C9")); c.setFont("Helvetica", 8.2); c.drawRightString(ANCHO - MARGEN, ALTO - h / 2 - 2.2 * mm, "Generado: " + info["generado"])
    c.restoreState()


def _interna(c, doc, info):
    c.saveState()
    c.setFillColor(NAVY); c.rect(0, ALTO - 15 * mm, ANCHO, 15 * mm, stroke=0, fill=1)
    c.setFillColor(AZUL); c.rect(0, ALTO - 16.2 * mm, ANCHO, 1.2 * mm, stroke=0, fill=1)
    if os.path.exists(LOGO):
        c.drawImage(LOGO, MARGEN, ALTO - 12.6 * mm, 10 * mm, 10 * mm, mask="auto")
    c.setFillColor(white); c.setFont("Helvetica-Bold", 11); c.drawString(MARGEN + 13 * mm, ALTO - 8.4 * mm, "SIGER")
    c.setFillColor(HexColor("#8FA8C9")); c.setFont("Helvetica", 8); c.drawRightString(ANCHO - MARGEN, ALTO - 8.4 * mm, "Informe de estadísticas · " + info["generado"])
    c.restoreState()


# ----------------------------------------------------------------- informe
def generar(d, info, fmt_min, nombre_tipo, label_prio, label_estado):
    """d: respuesta de /api/estadisticas. info: dict con generado, alcance, periodo, filtros (lista de (etiqueta, valor))."""
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=20 * mm, bottomMargin=19 * mm,
                          title="SIGER - Estadísticas de emergencias", author="SIGER", subject="Informe de estadísticas")
    f1 = Frame(MARGEN, 19 * mm, UTIL, ALTO - 19 * mm - 53 * mm, id="f1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    f2 = Frame(MARGEN, 19 * mm, UTIL, ALTO - 19 * mm - 23 * mm, id="f2", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p1", frames=[f1], onPage=lambda c, dd: _portada(c, dd, info), autoNextPageTemplate="p2"),
                          PageTemplate(id="p2", frames=[f2], onPage=lambda c, dd: _interna(c, dd, info))])
    k = d["kpis"]
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=TEXTO)
    sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=9.4, leading=14, textColor=GRIS, alignment=TA_LEFT)
    cel = ParagraphStyle("cel", fontName="Helvetica", fontSize=8.4, leading=11, textColor=TEXTO)
    cab = ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=6.8, leading=9, textColor=GRIS)
    nota = ParagraphStyle("nota", fontName="Helvetica", fontSize=7.8, leading=11.5, textColor=GRIS)

    S = [Paragraph("Estadísticas de emergencias", h1), Spacer(1, 1.5 * mm),
         Paragraph(info["alcance"] + ". Los datos corresponden a los incidentes registrados en el sistema.", sub), Spacer(1, 4.5 * mm)]
    # filtros aplicados
    filtros = info["filtros"]
    cols = len(filtros); cw = UTIL / cols
    t = Table([[Paragraph(e.upper(), cab) for e, _ in filtros], [Paragraph(str(v), cel) for _, v in filtros]], colWidths=[cw] * cols)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FONDO), ("BOX", (0, 0), (-1, -1), 0.7, BORDE), ("LINEAFTER", (0, 0), (-2, -1), 0.5, BORDE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3.2 * mm), ("TOPPADDING", (0, 0), (-1, 0), 2.6 * mm), ("BOTTOMPADDING", (0, 1), (-1, 1), 2.6 * mm),
                           ("TOPPADDING", (0, 1), (-1, 1), 0.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, 0), 0)]))
    S += [t, Spacer(1, 6 * mm)]

    S += [Titulo("Indicadores principales"),
          Kpis([("Total de emergencias", _num(k["total"]), f"{_num(k['afectados'])} personas afectadas · {_num(k['heridos'])} heridos", AZUL),
                ("Emergencias activas", _num(k["activas"]), f"{_pct(k['pct_activas'])} del total", AZUL_CL),
                ("Emergencias resueltas", _num(k["resueltas"]), f"{_pct(k['pct_resueltas'])} del total", VERDE),
                ("Críticas activas", _num(k["criticas_activas"]), "Requieren atención inmediata", ROJO),
                ("Tiempo prom. de respuesta", fmt_min(k["tiempo_respuesta_min"]), f"Reporte a asignación · {_num(k['con_tiempo_respuesta'])} casos", AMBAR),
                ("Tiempo prom. de atención", fmt_min(k["tiempo_atencion_min"]), f"Reporte a resolución · {_num(k['con_tiempo_atencion'])} casos", AMBAR)]),
          Spacer(1, 7 * mm)]

    if k["total"] == 0:
        S += [Spacer(1, 6 * mm), Paragraph("No hay emergencias registradas con los filtros seleccionados.", sub)]
    else:
        gran = d["serie"]["granularidad"]
        S += [KeepTogether([Titulo("Emergencias en el tiempo", "Reportes por " + ("mes" if gran == "mes" else "día")), Area(d["serie"])]), Spacer(1, 7 * mm)]
        mitad = (UTIL - 8 * mm) / 2
        dos = Table([[Titulo("Por estado"), Titulo("Por prioridad")],
                     [Dona(d["por_estado"], COLOR_ESTADO, label_estado), Dona(d["por_prioridad"], COLOR_PRIO, label_prio)]],
                    colWidths=[mitad, mitad + 8 * mm])
        dos.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 8 * mm), ("RIGHTPADDING", (1, 0), (1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        S += [KeepTogether([dos]), Spacer(1, 7 * mm)]
        S += [KeepTogether([Titulo("Por tipo de emergencia", "Porcentaje sobre el total"), Barras(d["por_tipo"], AZUL, nombre_tipo)]), Spacer(1, 7 * mm)]
        if info.get("es_admin"):
            S += [KeepTogether([Titulo("Por municipio", "Porcentaje sobre el total"), Barras(d["por_municipio"], AZUL_CL)]), Spacer(1, 7 * mm)]
        if d.get("por_organismo"):
            S += [KeepTogether([Titulo("Organismos con más emergencias asignadas", "Excluye pendientes y descartadas"), Barras(d["por_organismo"], TURQ, ancho_nombre=0.4)]), Spacer(1, 7 * mm)]
        S += [Paragraph("<b>Notas.</b> Activas: pendientes, asignadas y en atención. Resueltas: resueltas y cerradas. "
                        "Tiempo de respuesta: del reporte a la primera asignación a un organismo. Tiempo de atención: del reporte a su resolución. "
                        "Los promedios solo consideran las emergencias que ya tienen ese evento registrado.", nota)]
    doc.build(S, canvasmaker=_Numerado)
    return buf.getvalue()
