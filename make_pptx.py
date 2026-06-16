"""OpenAlio MCP 발표자료 생성 스크립트"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import copy

# ── 색상 팔레트 ──────────────────────────────────────────────────
NAVY      = RGBColor(0x0D, 0x47, 0xA1)   # 진한 파랑
BLUE      = RGBColor(0x15, 0x65, 0xC0)   # 중간 파랑
LIGHTBLUE = RGBColor(0xBB, 0xDE, 0xFB)   # 연한 파랑 배경
TEAL      = RGBColor(0x00, 0x89, 0x7B)   # 청록
ORANGE    = RGBColor(0xE6, 0x51, 0x00)   # 강조 오렌지
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
DARK_GRAY = RGBColor(0x21, 0x21, 0x21)
MID_GRAY  = RGBColor(0x61, 0x61, 0x61)
LIGHT_GRAY= RGBColor(0xF5, 0xF5, 0xF5)
GOLD      = RGBColor(0xF5, 0x7F, 0x17)

W = Inches(13.33)   # 와이드 슬라이드 너비
H = Inches(7.5)     # 높이

prs = Presentation()
prs.slide_width  = W
prs.slide_height = H

blank_layout = prs.slide_layouts[6]  # 빈 레이아웃

# ── 공통 헬퍼 ────────────────────────────────────────────────────
def add_rect(slide, x, y, w, h, fill=None, line=None, line_width=None):
    shape = slide.shapes.add_shape(1, x, y, w, h)  # MSO_SHAPE_TYPE.RECTANGLE
    fill_fmt = shape.fill
    if fill:
        fill_fmt.solid()
        fill_fmt.fore_color.rgb = fill
    else:
        fill_fmt.background()
    line_fmt = shape.line
    if line:
        line_fmt.color.rgb = line
        if line_width:
            line_fmt.width = line_width
    else:
        line_fmt.fill.background()
    return shape


def txb(slide, text, x, y, w, h,
        size=18, bold=False, color=DARK_GRAY,
        align=PP_ALIGN.LEFT, italic=False, wrap=True):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.color.rgb = color
    run.font.italic = italic
    return tb


def add_paragraph(tf, text, size=16, bold=False, color=DARK_GRAY,
                  align=PP_ALIGN.LEFT, space_before=Pt(4), italic=False):
    p = tf.add_paragraph()
    p.alignment = align
    p.space_before = space_before
    run = p.add_run()
    run.text = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.color.rgb = color
    run.font.italic = italic
    return p


def slide_header(slide, title, subtitle=None, bg=NAVY):
    """상단 헤더 바"""
    add_rect(slide, 0, 0, W, Inches(1.3), fill=bg)
    txb(slide, title,
        Inches(0.5), Inches(0.12), Inches(11), Inches(0.8),
        size=30, bold=True, color=WHITE)
    if subtitle:
        txb(slide, subtitle,
            Inches(0.5), Inches(0.88), Inches(11), Inches(0.4),
            size=14, color=LIGHTBLUE, italic=True)


def footer_bar(slide, slide_num, total=15):
    """하단 슬라이드 번호 바"""
    add_rect(slide, 0, H - Inches(0.38), W, Inches(0.38), fill=NAVY)
    txb(slide, f"OpenAlio MCP  |  {slide_num} / {total}",
        Inches(0.3), H - Inches(0.36), Inches(6), Inches(0.34),
        size=10, color=RGBColor(0xBB, 0xDE, 0xFB))


def bullet_box(slide, items, x, y, w, h,
               bullet="•", size=17, color=DARK_GRAY, line_h=Pt(8)):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    first = True
    for item in items:
        if first:
            p = tf.paragraphs[0]
            first = False
        else:
            p = tf.add_paragraph()
        p.space_before = line_h
        run = p.add_run()
        run.text = f"{bullet}  {item}"
        run.font.size = Pt(size)
        run.font.color.rgb = color


def flow_box(slide, labels, x, y, box_w=Inches(1.8), box_h=Inches(0.6),
             gap=Inches(0.3), fill=BLUE, text_color=WHITE, text_size=14,
             direction="vertical", arrow_color=NAVY):
    """수직/수평 플로우 다이어그램 (박스 + 화살표)"""
    positions = []
    for i, label in enumerate(labels):
        if direction == "vertical":
            bx, by = x, y + i * (box_h + gap)
        else:
            bx, by = x + i * (box_w + gap), y
        add_rect(slide, bx, by, box_w, box_h, fill=fill)
        txb(slide, label, bx, by + Pt(4), box_w, box_h,
            size=text_size, bold=True, color=text_color, align=PP_ALIGN.CENTER)
        positions.append((bx, by))
        # 화살표
        if i < len(labels) - 1:
            if direction == "vertical":
                ax = bx + box_w / 2 - Inches(0.05)
                ay = by + box_h
                aw, ah = Inches(0.1), gap
            else:
                ax = bx + box_w
                ay = by + box_h / 2 - Inches(0.05)
                aw, ah = gap, Inches(0.1)
            add_rect(slide, ax, ay, aw, ah, fill=arrow_color)
    return positions


# ════════════════════════════════════════════════════════════════
#  슬라이드 01 – 표지
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
bg = add_rect(slide, 0, 0, W, H, fill=NAVY)

# 대각선 장식 박스
add_rect(slide, W - Inches(4), 0, Inches(4), H, fill=BLUE)
add_rect(slide, W - Inches(4.1), Inches(0.5), Inches(0.15), H - Inches(1), fill=GOLD)

# 로고/아이콘 텍스트
txb(slide, "🔗", Inches(8.8), Inches(0.8), Inches(2), Inches(2), size=72, align=PP_ALIGN.CENTER)

# 제목
txb(slide, "OpenAlio MCP",
    Inches(0.7), Inches(1.8), Inches(7.5), Inches(1.4),
    size=52, bold=True, color=WHITE)

# 부제
txb(slide, "공공기관 정보공개의 AI 활용성 제고를 위한",
    Inches(0.7), Inches(3.35), Inches(7.5), Inches(0.6),
    size=20, color=LIGHTBLUE)
txb(slide, "MCP 기반 실험",
    Inches(0.7), Inches(3.9), Inches(7.5), Inches(0.6),
    size=20, color=LIGHTBLUE)

# 구분선
add_rect(slide, Inches(0.7), Inches(4.6), Inches(4.5), Inches(0.06), fill=GOLD)

# 발표자 정보
txb(slide, "김보성 사무관",
    Inches(0.7), Inches(4.85), Inches(5), Inches(0.55),
    size=20, bold=True, color=WHITE)
txb(slide, "재경부 공공정책국",
    Inches(0.7), Inches(5.35), Inches(5), Inches(0.5),
    size=16, color=LIGHTBLUE)

txb(slide, "2026. 06.",
    Inches(0.7), Inches(6.3), Inches(3), Inches(0.45),
    size=13, color=RGBColor(0x90, 0xCA, 0xF9))

# ════════════════════════════════════════════════════════════════
#  슬라이드 02 – ALIO 소개
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "01  공공기관 정보공개의 성공, ALIO",
             "ALIO는 공공기관 투명성 제고를 위한 대표적인 성공 사례")
footer_bar(slide, 1)

# 왼쪽 내용
add_rect(slide, Inches(0.4), Inches(1.45), Inches(5.6), Inches(5.3), fill=WHITE)
txb(slide, "ALIO의 핵심 가치",
    Inches(0.6), Inches(1.6), Inches(5), Inches(0.55),
    size=18, bold=True, color=NAVY)

items = [
    "공공기관 경영정보 대국민 공개",
    "국민 알권리 확대",
    "공공기관 책임성 강화",
    "355개 공공기관 정보 통합 제공",
    "재무·인사·경영평가 등 50개 공시항목",
]
bullet_box(slide, items, Inches(0.7), Inches(2.25), Inches(5.1), Inches(4),
           size=16, color=DARK_GRAY)

# 오른쪽 – 발전 타임라인
add_rect(slide, Inches(6.4), Inches(1.45), Inches(6.5), Inches(5.3), fill=WHITE)
txb(slide, "서비스 발전 연혁",
    Inches(6.6), Inches(1.6), Inches(6), Inches(0.55),
    size=18, bold=True, color=NAVY)

timeline = [
    ("2005", "ALIO 출범", "공공기관 경영정보 최초 공개", BLUE),
    ("2014", "ALIO PLUS", "채용·시설·사업 정보 통합", TEAL),
    ("2019", "JOB-ALIO", "공공기관 채용정보 전문 서비스", ORANGE),
    ("2026", "OpenAlio MCP", "AI 활용 가능 개방형 인터페이스", GOLD),
]
ty = Inches(2.2)
for year, name, desc, col in timeline:
    add_rect(slide, Inches(6.7), ty, Inches(0.85), Inches(0.5), fill=col)
    txb(slide, year, Inches(6.7), ty, Inches(0.85), Inches(0.5),
        size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    txb(slide, name, Inches(7.7), ty - Inches(0.02), Inches(2.5), Inches(0.35),
        size=15, bold=True, color=col)
    txb(slide, desc, Inches(7.7), ty + Inches(0.28), Inches(4.9), Inches(0.3),
        size=12, color=MID_GRAY)
    if year != "2026":
        add_rect(slide, Inches(7.1), ty + Inches(0.5), Inches(0.05), Inches(0.42), fill=MID_GRAY)
    ty += Inches(0.98)

# ════════════════════════════════════════════════════════════════
#  슬라이드 03 – AI 시대의 새로운 과제
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "02  그러나 AI 시대의 새로운 과제",
             "정보 공개는 성공했지만 정보 활용은 여전히 어렵다")
footer_bar(slide, 2)

# 왼쪽 – 분산된 정보원
add_rect(slide, Inches(0.4), Inches(1.45), Inches(5.6), Inches(5.3), fill=WHITE)
txb(slide, "공공기관 정보, 어디에 흩어져 있나?",
    Inches(0.6), Inches(1.6), Inches(5.2), Inches(0.55),
    size=17, bold=True, color=NAVY)

sources = ["ALIO", "ALIO PLUS", "JOB-ALIO",
           "기관 홈페이지", "법령 / 지침 / 편람", "뉴스 / 보도자료"]
sy = Inches(2.3)
for s in sources:
    add_rect(slide, Inches(0.8), sy, Inches(4.8), Inches(0.55), fill=LIGHTBLUE)
    txb(slide, s, Inches(0.85), sy + Inches(0.05), Inches(4.6), Inches(0.45),
        size=15, bold=True, color=NAVY)
    sy += Inches(0.65)

# 오른쪽 – 문제점
add_rect(slide, Inches(6.4), Inches(1.45), Inches(6.5), Inches(5.3), fill=WHITE)
txb(slide, "AI가 활용하기 어려운 이유",
    Inches(6.6), Inches(1.6), Inches(6), Inches(0.55),
    size=17, bold=True, color=NAVY)

problems = [
    ("분산성", "여러 사이트에 나뉜 정보"),
    ("비구조성", "PDF·엑셀·웹페이지 혼재"),
    ("비연결성", "기관 간 비교 불가"),
    ("저기계가독성", "AI 직접 활용 어려움"),
]
py = Inches(2.3)
for title, desc in problems:
    add_rect(slide, Inches(6.6), py, Inches(0.08), Inches(0.6), fill=ORANGE)
    txb(slide, title, Inches(6.85), py, Inches(2.5), Inches(0.35),
        size=15, bold=True, color=ORANGE)
    txb(slide, desc, Inches(6.85), py + Inches(0.3), Inches(5.8), Inches(0.35),
        size=13, color=MID_GRAY)
    py += Inches(0.9)

txb(slide, "→ 정보는 공개됐지만, AI는 아직 '읽지 못한다'",
    Inches(6.5), Inches(6.2), Inches(6.3), Inches(0.5),
    size=14, bold=True, color=NAVY, italic=True)

# ════════════════════════════════════════════════════════════════
#  슬라이드 04 – 국민 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "03  국민 입장에서의 Pain Point",
             "정보는 공개되어 있으나 질문하기 어렵다")
footer_bar(slide, 3)

# 질문 박스
add_rect(slide, Inches(0.4), Inches(1.45), W - Inches(0.8), Inches(0.85), fill=NAVY)
txb(slide, '💬  "한국전력의 최근 5년 부채 추이는?"',
    Inches(0.6), Inches(1.55), W - Inches(1), Inches(0.65),
    size=22, bold=True, color=WHITE)

# 현재 절차 (왼쪽)
add_rect(slide, Inches(0.4), Inches(2.5), Inches(5.8), Inches(4.3), fill=WHITE)
txb(slide, "현재 절차 (Before)",
    Inches(0.6), Inches(2.6), Inches(5.4), Inches(0.5),
    size=17, bold=True, color=ORANGE)

steps = ["① ALIO 접속", "② 기관 검색", "③ 재무현황 이동",
         "④ 자료 다운로드", "⑤ 직접 분석"]
flow_box(slide, steps,
         x=Inches(1.2), y=Inches(3.15),
         box_w=Inches(3.5), box_h=Inches(0.48),
         gap=Inches(0.18), fill=RGBColor(0xFF, 0xCC, 0xBC),
         text_color=DARK_GRAY, text_size=14)

# AI 활용 (오른쪽)
add_rect(slide, Inches(6.6), Inches(2.5), Inches(6.3), Inches(4.3), fill=WHITE)
txb(slide, "OpenAlio MCP 활용 (After)",
    Inches(6.8), Inches(2.6), Inches(5.9), Inches(0.5),
    size=17, bold=True, color=TEAL)

ai_steps = ["질문 입력", "AI + OpenAlio MCP", "즉시 분석·시각화"]
flow_box(slide, ai_steps,
         x=Inches(7.6), y=Inches(3.15),
         box_w=Inches(4), box_h=Inches(0.55),
         gap=Inches(0.3), fill=TEAL,
         text_color=WHITE, text_size=15)

# 추가 사례
txb(slide, "다른 예시 질문",
    Inches(6.8), Inches(5.5), Inches(5.9), Inches(0.4),
    size=14, bold=True, color=MID_GRAY)
more = ["임원 보수 순위 비교", "부채 증가율 상위 기관", "기관 간 실시간 비교"]
bullet_box(slide, more, Inches(6.8), Inches(5.85), Inches(5.9), Inches(0.9),
           size=13, color=MID_GRAY)

# ════════════════════════════════════════════════════════════════
#  슬라이드 05 – 공공기관 실무자 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "04  공공기관 실무자 입장에서의 Pain Point",
             "벤치마킹과 업무학습 비용이 높다")
footer_bar(slide, 4)

cards = [
    ("유사기관 운영사례 탐색",
     "동종 기관 운영사례를\n여러 사이트에서 수작업으로 수집",
     BLUE),
    ("경영평가 대응사례 확인",
     "지적사항·우수사례 PDF를\n일일이 검토해야 함",
     TEAL),
    ("신규 담당자 업무학습",
     "법령·지침·편람이 분산돼\n온보딩 비용 과다",
     ORANGE),
]
cx = Inches(0.5)
for title, desc, col in cards:
    add_rect(slide, cx, Inches(1.55), Inches(3.9), Inches(4.5), fill=WHITE)
    add_rect(slide, cx, Inches(1.55), Inches(3.9), Inches(0.55), fill=col)
    txb(slide, title, cx + Inches(0.1), Inches(1.62),
        Inches(3.7), Inches(0.45), size=17, bold=True, color=WHITE)
    txb(slide, desc, cx + Inches(0.2), Inches(2.3),
        Inches(3.5), Inches(2.5), size=15, color=DARK_GRAY)
    cx += Inches(4.3)

# 하단 요약
add_rect(slide, Inches(0.4), Inches(6.2), W - Inches(0.8), Inches(0.85), fill=NAVY)
txb(slide, "→ OpenAlio MCP: AI에게 물어보면 즉시 정리된 벤치마킹 결과 제공",
    Inches(0.6), Inches(6.3), W - Inches(1), Inches(0.65),
    size=18, bold=True, color=WHITE)

# ════════════════════════════════════════════════════════════════
#  슬라이드 06 – 재경부 공무원 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "05  재경부·주무부처 공무원 입장에서의 Pain Point",
             "공개된 데이터를 활용하는 데 많은 행정비용이 발생")
footer_bar(slide, 5)

# 업무 유형
add_rect(slide, Inches(0.4), Inches(1.45), Inches(4.2), Inches(5.3), fill=WHITE)
txb(slide, "주요 업무 유형",
    Inches(0.6), Inches(1.6), Inches(4), Inches(0.5),
    size=17, bold=True, color=NAVY)

tasks = ["기능개혁 검토", "증원심사", "경영평가 지원",
         "기관 통합 검토", "보도 대응", "팩트체크"]
ty2 = Inches(2.25)
for t in tasks:
    add_rect(slide, Inches(0.7), ty2, Inches(3.5), Inches(0.52), fill=LIGHTBLUE)
    txb(slide, t, Inches(0.75), ty2 + Inches(0.06),
        Inches(3.4), Inches(0.42), size=15, bold=True, color=NAVY)
    ty2 += Inches(0.65)

# 실제 업무 흐름
add_rect(slide, Inches(4.9), Inches(1.45), Inches(7.9), Inches(5.3), fill=WHITE)
txb(slide, "실제 업무 흐름 (현재)",
    Inches(5.1), Inches(1.6), Inches(7.5), Inches(0.5),
    size=17, bold=True, color=ORANGE)

flow_steps = [
    "기관별 정원·재무·사업 정보 확인 필요",
    "ALIO 접속 → 각 항목 클릭 → 엑셀 다운로드",
    "파일 수작업 정리 및 가공",
    "분석 수행",
    "보고서 작성",
]
fy = Inches(2.25)
for i, step in enumerate(flow_steps):
    col = ORANGE if i == 1 or i == 2 else BLUE
    add_rect(slide, Inches(5.2), fy, Inches(7.2), Inches(0.52), fill=col)
    txb(slide, step, Inches(5.3), fy + Inches(0.06),
        Inches(7.0), Inches(0.42), size=14, bold=(i in [1,2]), color=WHITE)
    if i < len(flow_steps) - 1:
        add_rect(slide, Inches(8.7), fy + Inches(0.52),
                 Inches(0.08), Inches(0.14), fill=MID_GRAY)
    fy += Inches(0.68)

txb(slide, "⚠  기관 하나당 수십 개 파일, 수백 개 기관 = 막대한 행정비용",
    Inches(5.1), Inches(6.2), Inches(7.8), Inches(0.5),
    size=14, bold=True, color=ORANGE, italic=True)

# ════════════════════════════════════════════════════════════════
#  슬라이드 07 – 연구자 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "06  연구자 입장에서의 Pain Point",
             "데이터보다 데이터 준비에 더 많은 시간이 소요")
footer_bar(slide, 6)

# 중앙 원형 다이어그램 대신 사이클 박스
txb(slide, "데이터 준비에 소요되는 연구 시간",
    Inches(2), Inches(1.5), Inches(9), Inches(0.6),
    size=22, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

cycle_items = [
    ("수집", "ALIO·기관 홈페이지\n수작업 다운로드", BLUE),
    ("정제", "이상값·결측값\n수동 처리", TEAL),
    ("통합", "기관 코드 통일\n형식 표준화", ORANGE),
    ("전처리", "분석 가능한\n형태로 변환", NAVY),
]
cx2 = Inches(0.8)
for title, desc, col in cycle_items:
    add_rect(slide, cx2, Inches(2.5), Inches(2.8), Inches(3.2), fill=col)
    txb(slide, title, cx2, Inches(2.6), Inches(2.8), Inches(0.6),
        size=22, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    txb(slide, desc, cx2 + Inches(0.1), Inches(3.3),
        Inches(2.6), Inches(2), size=14, color=WHITE, align=PP_ALIGN.CENTER)
    if title != "전처리":
        add_rect(slide, cx2 + Inches(2.8), Inches(3.8),
                 Inches(0.4), Inches(0.12), fill=WHITE)
    cx2 += Inches(3.2)

# 반복 표시
txb(slide, "⟳  위 과정을 매 연구마다 반복",
    Inches(3), Inches(5.9), Inches(7), Inches(0.5),
    size=17, bold=True, color=MID_GRAY, align=PP_ALIGN.CENTER)

add_rect(slide, Inches(0.5), Inches(6.4), W - Inches(1), Inches(0.75), fill=NAVY)
txb(slide, "→ OpenAlio MCP: 정제된 11개 메트릭 × 355개 기관 × 6년치 즉시 제공",
    Inches(0.7), Inches(6.5), W - Inches(1.4), Inches(0.55),
    size=17, bold=True, color=WHITE)

# ════════════════════════════════════════════════════════════════
#  슬라이드 08 – OpenAlio MCP 개발
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "07  그래서 OpenAlio MCP를 개발",
             "공공기관 정보를 AI가 활용할 수 있도록 연결")
footer_bar(slide, 7)

# 좌측 데이터소스
add_rect(slide, Inches(0.4), Inches(1.45), Inches(3.2), Inches(5.3), fill=WHITE)
txb(slide, "데이터 소스",
    Inches(0.6), Inches(1.6), Inches(3), Inches(0.5),
    size=17, bold=True, color=NAVY)

sources2 = ["ALIO", "ALIO PLUS", "JOB-ALIO", "법령·지침", "편람", "뉴스"]
sy2 = Inches(2.25)
for s in sources2:
    add_rect(slide, Inches(0.7), sy2, Inches(2.6), Inches(0.5), fill=LIGHTBLUE)
    txb(slide, s, Inches(0.75), sy2 + Inches(0.06),
        Inches(2.5), Inches(0.4), size=14, bold=True, color=NAVY)
    sy2 += Inches(0.62)

# 중앙 – MCP 박스
add_rect(slide, Inches(4.0), Inches(2.5), Inches(5.2), Inches(2.3), fill=NAVY)
txb(slide, "OpenAlio MCP",
    Inches(4.0), Inches(2.8), Inches(5.2), Inches(0.8),
    size=26, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
txb(slide, "32개 도구 · 2개 프롬프트 · 5개 리소스",
    Inches(4.0), Inches(3.55), Inches(5.2), Inches(0.45),
    size=13, color=LIGHTBLUE, align=PP_ALIGN.CENTER)

# 화살표 (소스 → MCP)
add_rect(slide, Inches(3.6), Inches(3.45), Inches(0.42), Inches(0.12), fill=GOLD)

# 화살표 (MCP → 활용)
add_rect(slide, Inches(9.2), Inches(3.45), Inches(0.42), Inches(0.12), fill=GOLD)

# 우측 – 활용 대상
add_rect(slide, Inches(9.9), Inches(1.45), Inches(3.0), Inches(5.3), fill=WHITE)
txb(slide, "활용 대상",
    Inches(10.1), Inches(1.6), Inches(2.8), Inches(0.5),
    size=17, bold=True, color=NAVY)

users = [
    ("국민", "정보 조회·질문", BLUE),
    ("공공기관", "벤치마킹·학습", TEAL),
    ("공무원", "업무 자동화", ORANGE),
    ("연구자", "데이터 분석", NAVY),
]
uy = Inches(2.25)
for uname, udesc, ucol in users:
    add_rect(slide, Inches(10.1), uy, Inches(2.5), Inches(0.85), fill=ucol)
    txb(slide, uname, Inches(10.15), uy + Inches(0.04),
        Inches(2.4), Inches(0.38), size=16, bold=True, color=WHITE)
    txb(slide, udesc, Inches(10.15), uy + Inches(0.42),
        Inches(2.4), Inches(0.35), size=12, color=WHITE)
    uy += Inches(1.0)

# 핵심 문장
add_rect(slide, Inches(0.4), Inches(6.9), W - Inches(0.8), Inches(0.42), fill=GOLD)
txb(slide, "공공기관 정보를 AI가 활용 가능한 형태로 연결하는 개방형 인터페이스",
    Inches(0.6), Inches(6.92), W - Inches(1.2), Inches(0.38),
    size=16, bold=True, color=DARK_GRAY, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  슬라이드 09 – MCP란 무엇인가
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "08  MCP란 무엇인가",
             "MCP는 AI 시대의 USB-C")
footer_bar(slide, 8)

# 왼쪽 – USB 비유
add_rect(slide, Inches(0.4), Inches(1.45), Inches(5.8), Inches(5.3), fill=WHITE)
txb(slide, "USB-C 비유",
    Inches(0.6), Inches(1.6), Inches(5.4), Inches(0.5),
    size=17, bold=True, color=NAVY)

usb_old = ["스마트폰", "태블릿", "노트북", "카메라"]
usb_steps_old = [f"┌ {d}" for d in usb_old]

txb(slide, "Before: 기기마다 다른 충전기",
    Inches(0.7), Inches(2.15), Inches(5), Inches(0.4),
    size=14, bold=True, color=ORANGE)
oy = Inches(2.65)
for item in usb_old:
    add_rect(slide, Inches(0.8), oy, Inches(2.0), Inches(0.4),
             fill=RGBColor(0xFF, 0xCC, 0xBC))
    txb(slide, item, Inches(0.85), oy + Inches(0.04),
        Inches(1.9), Inches(0.35), size=13, color=DARK_GRAY)
    add_rect(slide, Inches(2.8), oy + Inches(0.15),
             Inches(0.5), Inches(0.08), fill=ORANGE)
    add_rect(slide, Inches(3.3), oy, Inches(1.5), Inches(0.4),
             fill=ORANGE)
    txb(slide, "전용 충전기", Inches(3.35), oy + Inches(0.04),
        Inches(1.4), Inches(0.35), size=11, color=WHITE)
    oy += Inches(0.52)

txb(slide, "After: USB-C 하나로 모든 기기",
    Inches(0.7), Inches(4.9), Inches(5), Inches(0.4),
    size=14, bold=True, color=TEAL)
devices = ["스마트폰", "태블릿", "노트북", "카메라"]
dx = Inches(0.8)
for d in devices:
    add_rect(slide, dx, Inches(5.4), Inches(1.0), Inches(0.45), fill=LIGHTBLUE)
    txb(slide, d, dx, Inches(5.43), Inches(1.0), Inches(0.4),
        size=11, color=NAVY, align=PP_ALIGN.CENTER)
    dx += Inches(1.1)
add_rect(slide, Inches(1.9), Inches(5.9), Inches(2.5), Inches(0.06), fill=TEAL)
add_rect(slide, Inches(3.15), Inches(5.95), Inches(0.08), Inches(0.35), fill=TEAL)
add_rect(slide, Inches(2.7), Inches(6.3), Inches(1.0), Inches(0.4), fill=TEAL)
txb(slide, "USB-C", Inches(2.7), Inches(6.32), Inches(1.0), Inches(0.38),
    size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# 오른쪽 – MCP 설명
add_rect(slide, Inches(6.4), Inches(1.45), Inches(6.5), Inches(5.3), fill=WHITE)
txb(slide, "MCP = Model Context Protocol",
    Inches(6.6), Inches(1.6), Inches(6.2), Inches(0.5),
    size=17, bold=True, color=NAVY)

txb(slide, "AI 모델이 다양한 데이터 소스와\n표준화된 방식으로 연결하는 프로토콜",
    Inches(6.6), Inches(2.2), Inches(6.1), Inches(0.85),
    size=15, color=DARK_GRAY)

mcp_sources = ["ALIO 경영정보", "법령·지침", "JOB-ALIO 채용", "뉴스"]
mx = Inches(6.7)
for ms in mcp_sources:
    add_rect(slide, mx, Inches(3.2), Inches(1.3), Inches(0.45), fill=LIGHTBLUE)
    txb(slide, ms, mx, Inches(3.22), Inches(1.3), Inches(0.42),
        size=11, color=NAVY, align=PP_ALIGN.CENTER)
    mx += Inches(1.5)
add_rect(slide, Inches(7.65), Inches(3.65), Inches(4.4), Inches(0.08), fill=NAVY)
add_rect(slide, Inches(9.7), Inches(3.73), Inches(0.1), Inches(0.35), fill=NAVY)
add_rect(slide, Inches(9.3), Inches(4.08), Inches(1.0), Inches(0.5), fill=NAVY)
txb(slide, "MCP", Inches(9.3), Inches(4.1), Inches(1.0), Inches(0.45),
    size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
add_rect(slide, Inches(9.7), Inches(4.58), Inches(0.1), Inches(0.3), fill=NAVY)
add_rect(slide, Inches(9.3), Inches(4.88), Inches(1.0), Inches(0.5), fill=BLUE)
txb(slide, "AI", Inches(9.3), Inches(4.9), Inches(1.0), Inches(0.45),
    size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

txb(slide, "→ 어떤 AI 서비스에도 동일한 방식으로 연결",
    Inches(6.6), Inches(5.6), Inches(6.2), Inches(0.4),
    size=13, bold=True, color=TEAL, italic=True)
txb(slide, "Claude / ChatGPT / Cursor / 브리티웍스 등",
    Inches(6.6), Inches(5.95), Inches(6.2), Inches(0.4),
    size=13, color=MID_GRAY, italic=True)

# ════════════════════════════════════════════════════════════════
#  슬라이드 10 – 작동 원리
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "09  OpenAlio MCP는 어떻게 동작하는가",
             "사용자 질문 → AI → MCP → 데이터 조회 → 분석 → 결과")
footer_bar(slide, 9)

# 중앙 플로우
flow_labels = [
    "사용자 질문",
    "AI (Claude / ChatGPT 등)",
    "OpenAlio MCP\n(32개 도구)",
    "ALIO · ALIO PLUS\n법령 · 뉴스 조회",
    "분석 수행",
    "표 · 그래프 · 보고서 생성",
]
flow_colors = [NAVY, BLUE, GOLD, TEAL, BLUE, NAVY]

box_w = Inches(4.0)
box_h = Inches(0.58)
gapv  = Inches(0.22)
start_x = (W - box_w) / 2
start_y = Inches(1.55)

for i, (label, col) in enumerate(zip(flow_labels, flow_colors)):
    by = start_y + i * (box_h + gapv)
    add_rect(slide, start_x, by, box_w, box_h, fill=col)
    txb(slide, label, start_x, by + Pt(3), box_w, box_h,
        size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    if i < len(flow_labels) - 1:
        ay = by + box_h
        add_rect(slide, start_x + box_w/2 - Inches(0.06),
                 ay, Inches(0.12), gapv, fill=MID_GRAY)

# 예시 질문 박스
add_rect(slide, Inches(0.4), Inches(1.55), Inches(3.0), Inches(5.5), fill=WHITE)
txb(slide, "예시 질문",
    Inches(0.6), Inches(1.68), Inches(2.8), Inches(0.45),
    size=15, bold=True, color=NAVY)
ex_q = [
    '"최근 5년간 부채 증가율\n상위 10개 기관"',
    '"A기관 B기관 통합 시\n영향 분석"',
    '"육아휴직 사용률이 가장\n높은 기관은?"',
]
eq_y = Inches(2.3)
for q in ex_q:
    add_rect(slide, Inches(0.55), eq_y, Inches(2.7), Inches(1.3),
             fill=LIGHTBLUE)
    txb(slide, q, Inches(0.6), eq_y + Inches(0.12),
        Inches(2.6), Inches(1.1), size=13, color=NAVY, italic=True)
    eq_y += Inches(1.5)

# 출력 예시 박스
add_rect(slide, Inches(9.8), Inches(1.55), Inches(3.1), Inches(5.5), fill=WHITE)
txb(slide, "출력 형태",
    Inches(10.0), Inches(1.68), Inches(2.9), Inches(0.45),
    size=15, bold=True, color=NAVY)
outputs = ["📊 시계열 차트", "📋 비교 표", "📝 보고서 초안", "🔗 출처 및 공시일"]
oy2 = Inches(2.3)
for o in outputs:
    add_rect(slide, Inches(10.0), oy2, Inches(2.7), Inches(0.65), fill=LIGHTBLUE)
    txb(slide, o, Inches(10.05), oy2 + Inches(0.1),
        Inches(2.6), Inches(0.5), size=14, color=NAVY)
    oy2 += Inches(0.82)

# ════════════════════════════════════════════════════════════════
#  슬라이드 11 – 활용 사례 ① 국민
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "10  활용 사례 ①  국민 서비스",
             "누구나 AI에게 물어보면 공공기관 정보를 즉시 확인")
footer_bar(slide, 10)

# 3개 사례 카드
citizen_cases = [
    ("💰", '"한전 부채 얼마야?"',
     "한국전력 최근 5년 부채 추이\n그래프 및 수치 즉시 제공"),
    ("👶", '"육아휴직 사용률이\n가장 높은 기관은?"',
     "355개 기관 육아휴직 데이터\n순위 표 자동 생성"),
    ("🏟️", '"근처 공공기관\n체육시설 알려줘"',
     "ALIO PLUS 시설 정보\n예약 링크·운영시간 안내"),
]
cx3 = Inches(0.4)
for icon, q, result in citizen_cases:
    add_rect(slide, cx3, Inches(1.55), Inches(3.95), Inches(5.1), fill=WHITE)
    txb(slide, icon, cx3, Inches(1.7), Inches(3.95), Inches(0.9),
        size=36, align=PP_ALIGN.CENTER)
    add_rect(slide, cx3, Inches(2.7), Inches(3.95), Inches(1.35), fill=NAVY)
    txb(slide, q, cx3 + Inches(0.1), Inches(2.76),
        Inches(3.75), Inches(1.2), size=16, bold=True, color=WHITE,
        align=PP_ALIGN.CENTER)
    txb(slide, "→ 결과", cx3 + Inches(0.2), Inches(4.2),
        Inches(3.5), Inches(0.4), size=13, bold=True, color=TEAL)
    txb(slide, result, cx3 + Inches(0.2), Inches(4.6),
        Inches(3.5), Inches(1.5), size=14, color=MID_GRAY)
    cx3 += Inches(4.3)

add_rect(slide, Inches(0.4), Inches(6.85), W - Inches(0.8), Inches(0.42), fill=TEAL)
txb(slide, "사용자는 웹사이트 구조를 몰라도 됩니다 — 질문만 하면 됩니다",
    Inches(0.6), Inches(6.87), W - Inches(1.2), Inches(0.38),
    size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  슬라이드 12 – 활용 사례 ② 공공기관 실무자
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "11  활용 사례 ②  공공기관 실무자",
             "벤치마킹·평가 대응·조직운영 정보를 즉시 활용")
footer_bar(slide, 11)

inst_cases = [
    ("ESG 우수사례 정리",
     '"유사기관 ESG 우수사례 정리"',
     "동종 기관 ESG 공시 항목\n우수 사례 자동 요약"),
    ("경영평가 지적사항",
     '"최근 경영평가 지적사항 분석"',
     "2025·2026 평가편람 기준\n지적 패턴 및 주요 지표 분석"),
    ("조직운영 비교",
     '"기관별 조직운영 비교"',
     "정원·실제 인력·보수 등\n11개 메트릭 동시 비교"),
]
ix = Inches(0.4)
for title, q, result in inst_cases:
    add_rect(slide, ix, Inches(1.55), Inches(3.95), Inches(5.1), fill=WHITE)
    add_rect(slide, ix, Inches(1.55), Inches(3.95), Inches(0.55), fill=TEAL)
    txb(slide, title, ix + Inches(0.1), Inches(1.6),
        Inches(3.75), Inches(0.45), size=16, bold=True, color=WHITE)
    add_rect(slide, ix + Inches(0.15), Inches(2.2),
             Inches(3.65), Inches(1.2), fill=LIGHTBLUE)
    txb(slide, q, ix + Inches(0.2), Inches(2.27),
        Inches(3.55), Inches(1.1), size=14, color=NAVY, italic=True)
    txb(slide, "출력 결과:", ix + Inches(0.2), Inches(3.55),
        Inches(3.5), Inches(0.38), size=13, bold=True, color=TEAL)
    txb(slide, result, ix + Inches(0.2), Inches(3.9),
        Inches(3.5), Inches(1.5), size=14, color=MID_GRAY)
    ix += Inches(4.3)

add_rect(slide, Inches(0.4), Inches(6.85), W - Inches(0.8), Inches(0.42), fill=TEAL)
txb(slide, "법령·지침·편람을 통합 검색 — 신규 담당자 온보딩 시간 대폭 단축",
    Inches(0.6), Inches(6.87), W - Inches(1.2), Inches(0.38),
    size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  슬라이드 13 – 활용 사례 ③ 재경부 업무 (★ 핵심)
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "12  활용 사례 ③  재경부 업무  ★",
             "기관 통합 검토 보고서를 AI가 자동으로 작성")
footer_bar(slide, 12)

# 강조 배경
add_rect(slide, Inches(0.4), Inches(1.45), W - Inches(0.8), Inches(1.05), fill=NAVY)
txb(slide, '질문:  "A기관과 B기관 통합 검토 보고서 작성해 줘"',
    Inches(0.65), Inches(1.58), W - Inches(1.3), Inches(0.8),
    size=22, bold=True, color=GOLD)

# 출력 항목
output_items = [
    ("재무현황", "부채·자산·수익\n최근 5년 추이", BLUE),
    ("인력현황", "정원·실인원·신규\n채용 현황", TEAL),
    ("주요사업", "기관 설립 목적\n및 핵심 기능", NAVY),
    ("지역 분포", "본사·지사 소재지\n지역별 인력", ORANGE),
    ("중복기능", "유사 기능 도출\n통합 시 효율", BLUE),
    ("기대효과", "통합 시나리오별\n예상 효과 요약", TEAL),
]
ox = Inches(0.5)
oy3 = Inches(2.7)
for i, (title, desc, col) in enumerate(output_items):
    if i == 3:
        ox = Inches(0.5)
        oy3 = Inches(4.65)
    add_rect(slide, ox, oy3, Inches(2.0), Inches(1.65), fill=col)
    txb(slide, title, ox + Inches(0.05), oy3 + Inches(0.08),
        Inches(1.9), Inches(0.45), size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    txb(slide, desc, ox + Inches(0.05), oy3 + Inches(0.6),
        Inches(1.9), Inches(0.95), size=13, color=WHITE, align=PP_ALIGN.CENTER)
    ox += Inches(2.25)

# 오른쪽 – 효과
add_rect(slide, Inches(7.0), Inches(2.65), Inches(5.9), Inches(3.65), fill=WHITE)
txb(slide, "기대 효과",
    Inches(7.2), Inches(2.8), Inches(5.6), Inches(0.5),
    size=17, bold=True, color=NAVY)

effects = [
    "수 시간 → 수 분으로 보고서 작성 시간 단축",
    "수작업 엑셀 다운로드 없이 자동 데이터 수집",
    "출처 자동 첨부 (공시일·API 기록 포함)",
    "증원심사·기능개혁 등 다양한 업무에 재활용",
]
ey = Inches(3.4)
for e in effects:
    add_rect(slide, Inches(7.2), ey, Inches(0.45), Inches(0.45), fill=GOLD)
    txb(slide, "✓", Inches(7.2), ey + Inches(0.02),
        Inches(0.45), Inches(0.42), size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    txb(slide, e, Inches(7.75), ey + Inches(0.04),
        Inches(4.9), Inches(0.42), size=14, color=DARK_GRAY)
    ey += Inches(0.65)

add_rect(slide, Inches(0.4), Inches(6.85), W - Inches(0.8), Inches(0.42), fill=GOLD)
txb(slide, "공개된 데이터 + AI = 행정 생산성의 획기적 향상",
    Inches(0.6), Inches(6.87), W - Inches(1.2), Inches(0.38),
    size=16, bold=True, color=DARK_GRAY, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  슬라이드 14 – 활용 사례 ④ 브리티웍스
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "13  활용 사례 ④  브리티웍스 및 지능형 업무시스템",
             "OpenAlio MCP는 특정 AI 서비스가 아닌 기반 인프라")
footer_bar(slide, 13)

# 중앙 아키텍처 다이어그램
txb(slide, "어떤 AI 시스템에도 연결 가능한 개방형 인터페이스",
    Inches(1.5), Inches(1.55), Inches(10), Inches(0.55),
    size=20, bold=True, color=NAVY, align=PP_ALIGN.CENTER)

# AI 서비스 레이어
ai_svcs = ["브리티웍스", "지능형 업무시스템", "Claude / ChatGPT", "향후 AI 플랫폼"]
ax2 = Inches(0.6)
for svc in ai_svcs:
    add_rect(slide, ax2, Inches(2.3), Inches(2.8), Inches(0.8), fill=BLUE)
    txb(slide, svc, ax2, Inches(2.32), Inches(2.8), Inches(0.75),
        size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    ax2 += Inches(3.1)

# 화살표 아래로
add_rect(slide, W/2 - Inches(0.06), Inches(3.1),
         Inches(0.12), Inches(0.4), fill=NAVY)
txb(slide, "▼", W/2 - Inches(0.3), Inches(3.3),
    Inches(0.6), Inches(0.3), size=14, color=NAVY, align=PP_ALIGN.CENTER)

# MCP 레이어
add_rect(slide, Inches(3.5), Inches(3.5), Inches(6.2), Inches(1.0), fill=GOLD)
txb(slide, "OpenAlio MCP  (표준 인터페이스)",
    Inches(3.5), Inches(3.65), Inches(6.2), Inches(0.7),
    size=22, bold=True, color=DARK_GRAY, align=PP_ALIGN.CENTER)

# 화살표 아래로
add_rect(slide, W/2 - Inches(0.06), Inches(4.5),
         Inches(0.12), Inches(0.4), fill=NAVY)

# 데이터 레이어
data_srcs = ["ALIO", "ALIO PLUS", "JOB-ALIO", "법령/지침"]
dx2 = Inches(1.0)
for ds in data_srcs:
    add_rect(slide, dx2, Inches(4.9), Inches(2.6), Inches(0.8), fill=TEAL)
    txb(slide, ds, dx2, Inches(4.92), Inches(2.6), Inches(0.75),
        size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    dx2 += Inches(2.85)

# 설명
add_rect(slide, Inches(0.4), Inches(5.95), W - Inches(0.8), Inches(0.75), fill=WHITE)
pts = [
    "표준화된 프로토콜(MCP)을 통해 어떤 AI 서비스도 동일한 방식으로 공공기관 데이터 활용",
    "브리티웍스·지능형 업무시스템에 MCP 서버로 연결 시 즉시 활용 가능",
    "새로운 AI 플랫폼 도입 시에도 OpenAlio MCP는 그대로 재사용",
]
py2 = Inches(6.0)
for pt in pts:
    txb(slide, f"• {pt}", Inches(0.6), py2, W - Inches(1.2), Inches(0.22),
        size=13, color=DARK_GRAY)
    py2 += Inches(0.23)

# ════════════════════════════════════════════════════════════════
#  슬라이드 15 – 향후 발전 방향
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=LIGHT_GRAY)
slide_header(slide, "14  향후 발전 방향",
             "단계적 확장을 통해 공공기관 정보공개 체계를 AI 시대에 맞게 고도화")
footer_bar(slide, 14)

roadmap = [
    ("대국민 서비스", BLUE, [
        "ALIO 챗봇 구현",
        "기관 비교 서비스",
        "정책 팩트체크",
    ]),
    ("내부 업무 지원", NAVY, [
        "증원심사 지원",
        "기능개혁 지원",
        "경영평가 지원",
        "언론 대응",
        "기관현황 자동 작성",
    ]),
    ("연구 활용", TEAL, [
        "공공기관 데이터\n분석 플랫폼",
        "평가결과 데이터 추가",
        "국회·조달 데이터 연계",
    ]),
    ("인프라 고도화", ORANGE, [
        "HTTP/SSE 서버 전환",
        "인증·속도제한 적용",
        "자동 업데이트 파이프라인",
        "보안 심의 대응",
    ]),
]
rx = Inches(0.4)
for title, col, items2 in roadmap:
    add_rect(slide, rx, Inches(1.55), Inches(2.95), Inches(5.2), fill=WHITE)
    add_rect(slide, rx, Inches(1.55), Inches(2.95), Inches(0.65), fill=col)
    txb(slide, title, rx + Inches(0.1), Inches(1.6),
        Inches(2.75), Inches(0.55), size=16, bold=True, color=WHITE)
    iy = Inches(2.35)
    for item in items2:
        add_rect(slide, rx + Inches(0.15), iy,
                 Inches(0.1), Inches(0.1), fill=col)
        txb(slide, item, rx + Inches(0.35), iy - Inches(0.02),
            Inches(2.45), Inches(0.6), size=13, color=DARK_GRAY)
        iy += Inches(0.65)
    rx += Inches(3.2)

add_rect(slide, Inches(0.4), Inches(6.85), W - Inches(0.8), Inches(0.42), fill=NAVY)
txb(slide, "현재 Phase 2 (로컬 MCP 서버) → Phase 4 (공개 HTTP 서버 + 인증 + 자동 업데이트)",
    Inches(0.6), Inches(6.87), W - Inches(1.2), Inches(0.38),
    size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  슬라이드 16 – 마무리
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
add_rect(slide, 0, 0, W, H, fill=NAVY)
add_rect(slide, W - Inches(4), 0, Inches(4), H, fill=BLUE)
add_rect(slide, W - Inches(4.1), Inches(0.5), Inches(0.15), H - Inches(1), fill=GOLD)

txb(slide, "마무리",
    Inches(0.7), Inches(0.8), Inches(7), Inches(0.7),
    size=28, bold=True, color=LIGHTBLUE)

txb(slide, "정보공개의 다음 단계는\n정보 활용",
    Inches(0.7), Inches(1.6), Inches(7), Inches(1.4),
    size=38, bold=True, color=WHITE)

add_rect(slide, Inches(0.7), Inches(3.1), Inches(5), Inches(0.06), fill=GOLD)

messages = [
    "OpenAlio MCP는 공공기관 정보공개 체계를 AI 시대에 맞게 확장하기 위한 실험입니다.",
    "궁극적으로는 국민과 행정이 공공기관 정보를 더 쉽고",
    "효과적으로 활용할 수 있도록 지원합니다.",
]
my = Inches(3.35)
for msg in messages:
    txb(slide, msg, Inches(0.7), my, Inches(7.5), Inches(0.5),
        size=17, color=LIGHTBLUE)
    my += Inches(0.48)

# 핵심 3요소
keywords = [
    ("개방성", "오픈소스\n누구나 기여"),
    ("연결성", "AI-데이터\n표준 연결"),
    ("활용성", "질문 한 번\n즉시 분석"),
]
kx = Inches(0.7)
for kword, kdesc in keywords:
    add_rect(slide, kx, Inches(5.0), Inches(1.8), Inches(1.8), fill=GOLD)
    txb(slide, kword, kx, Inches(5.1), Inches(1.8), Inches(0.7),
        size=20, bold=True, color=DARK_GRAY, align=PP_ALIGN.CENTER)
    txb(slide, kdesc, kx, Inches(5.75), Inches(1.8), Inches(0.9),
        size=13, color=DARK_GRAY, align=PP_ALIGN.CENTER)
    kx += Inches(2.1)

txb(slide, "감사합니다",
    Inches(0.7), Inches(6.5), Inches(5), Inches(0.7),
    size=28, bold=True, color=GOLD)

# ── 저장 ──────────────────────────────────────────────────────
out_path = "/home/user/open-ALIO-mcp/OpenAlio_MCP_발표자료.pptx"
prs.save(out_path)
print(f"저장 완료: {out_path}")
