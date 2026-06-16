"""OpenAlio MCP 발표자료 — 리디자인 (밝고 세련된 톤)"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── 슬라이드 크기 (16:9 와이드) ──────────────────────────────────
W = Inches(13.33)
H = Inches(7.5)

# ── 컬러 팔레트 (밝고 모던) ──────────────────────────────────────
# 베이스
BG        = RGBColor(0xF7, 0xF9, 0xFF)   # 아주 연한 블루-화이트
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
CARD      = RGBColor(0xFF, 0xFF, 0xFF)

# 주요 색
INDIGO    = RGBColor(0x3D, 0x5A, 0xFE)   # 선명한 인디고
INDIGO_D  = RGBColor(0x1A, 0x23, 0x7E)   # 짙은 인디고
INDIGO_L  = RGBColor(0xC5, 0xCA, 0xFF)   # 연한 인디고

CORAL     = RGBColor(0xFF, 0x6D, 0x00)   # 코럴 오렌지
CORAL_L   = RGBColor(0xFF, 0xE0, 0xCC)   # 연한 코럴

TEAL      = RGBColor(0x00, 0xB8, 0xD4)   # 밝은 틸
TEAL_D    = RGBColor(0x00, 0x83, 0x8F)
TEAL_L    = RGBColor(0xB2, 0xEB, 0xF2)   # 연한 틸

MINT      = RGBColor(0x00, 0xC8, 0x53)   # 민트 그린
MINT_L    = RGBColor(0xB9, 0xF6, 0xCA)

PURPLE    = RGBColor(0x7C, 0x4D, 0xFF)   # 소프트 퍼플
PURPLE_L  = RGBColor(0xEA, 0xE1, 0xFF)

AMBER     = RGBColor(0xFF, 0xC4, 0x00)   # 앰버 옐로
AMBER_D   = RGBColor(0xFF, 0x8F, 0x00)

# 텍스트
TXT_D     = RGBColor(0x1A, 0x1A, 0x2E)   # 거의 검정
TXT_M     = RGBColor(0x50, 0x56, 0x70)   # 중간 회색
TXT_L     = RGBColor(0x9E, 0xA3, 0xB8)   # 연한 회색

# 카드 구분선 색들
COLORS6   = [INDIGO, TEAL, CORAL, PURPLE, MINT, AMBER_D]

prs = Presentation()
prs.slide_width  = W
prs.slide_height = H
blank_layout = prs.slide_layouts[6]

# ── 헬퍼 함수 ────────────────────────────────────────────────────
def rect(slide, x, y, w, h, fill=None, line_color=None, line_w=Pt(1)):
    from pptx.util import Pt
    s = slide.shapes.add_shape(1, x, y, w, h)
    s.fill.solid() if fill else s.fill.background()
    if fill:
        s.fill.fore_color.rgb = fill
    s.line.fill.background()
    if line_color:
        s.line.color.rgb = line_color
        s.line.width = line_w
    return s

def tb(slide, text, x, y, w, h, size=14, bold=False,
        color=TXT_D, align=PP_ALIGN.LEFT, italic=False):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf  = box.text_frame
    tf.word_wrap = True
    p   = tf.paragraphs[0]
    p.alignment = align
    r   = p.add_run()
    r.text = text
    r.font.size   = Pt(size)
    r.font.bold   = bold
    r.font.italic = italic
    r.font.color.rgb = color
    return box

def add_p(tf, text, size=13, bold=False, color=TXT_D,
          align=PP_ALIGN.LEFT, space=Pt(5)):
    p = tf.add_paragraph()
    p.alignment   = align
    p.space_before = space
    r = p.add_run()
    r.text = text
    r.font.size  = Pt(size)
    r.font.bold  = bold
    r.font.color.rgb = color
    return p

def slide_bg(slide):
    rect(slide, 0, 0, W, H, fill=BG)

def header_band(slide, title, subtitle=None):
    """그라디언트 효과 헤더 (인디고 → 틸)"""
    rect(slide, 0, 0, W * 0.55, Inches(1.2), fill=INDIGO)
    rect(slide, W * 0.45, 0, W * 0.35, Inches(1.2), fill=TEAL)
    rect(slide, W * 0.75, 0, W * 0.25, Inches(1.2), fill=TEAL_D)
    # 흰 사선 장식
    rect(slide, W * 0.44, 0, Inches(0.12), Inches(1.2), fill=WHITE)
    rect(slide, W * 0.74, 0, Inches(0.08), Inches(1.2), fill=RGBColor(0xFF,0xFF,0xFF))
    tb(slide, title,
       Inches(0.5), Inches(0.1), Inches(10), Inches(0.65),
       size=26, bold=True, color=WHITE)
    if subtitle:
        tb(slide, subtitle,
           Inches(0.5), Inches(0.72), Inches(10), Inches(0.42),
           size=13, color=INDIGO_L, italic=True)

def footer(slide, num, total=15):
    rect(slide, 0, H - Inches(0.35), W, Inches(0.35), fill=INDIGO_D)
    tb(slide, "OpenAlio MCP",
       Inches(0.4), H - Inches(0.33), Inches(4), Inches(0.3),
       size=10, color=INDIGO_L)
    tb(slide, f"{num}  /  {total}",
       W - Inches(1.2), H - Inches(0.33), Inches(1.0), Inches(0.3),
       size=10, color=INDIGO_L, align=PP_ALIGN.RIGHT)

def card(slide, x, y, w, h, accent=INDIGO, accent_h=Inches(0.06)):
    """흰 카드 + 상단 컬러 테두리"""
    rect(slide, x, y, w, h, fill=WHITE,
         line_color=RGBColor(0xE8, 0xEC, 0xFF), line_w=Pt(0.75))
    rect(slide, x, y, w, accent_h, fill=accent)

def pill(slide, text, x, y, w=Inches(2.2), h=Inches(0.42),
         fill=INDIGO_L, color=INDIGO_D, size=13, bold=True):
    rect(slide, x, y, w, h, fill=fill)
    tb(slide, text, x, y + Pt(2), w, h, size=size, bold=bold,
       color=color, align=PP_ALIGN.CENTER)

def arrow_v(slide, x, y, h=Inches(0.28)):
    rect(slide, x - Inches(0.04), y, Inches(0.08), h, fill=TXT_L)

def flow_v(slide, labels, colors, x, cy, bw=Inches(4.5), bh=Inches(0.55), gap=Inches(0.25)):
    for i, (lbl, col) in enumerate(zip(labels, colors)):
        by = cy + i * (bh + gap)
        rect(slide, x, by, bw, bh, fill=col)
        tb(slide, lbl, x, by + Pt(3), bw, bh,
           size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        if i < len(labels) - 1:
            arrow_v(slide, x + bw / 2, by + bh, gap)

# ════════════════════════════════════════════════════════════════
#  S00 – 표지
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)

# 배경 분할: 왼쪽 진한 인디고, 오른쪽 밝은 패턴
rect(slide, 0, 0, W * 0.62, H, fill=INDIGO_D)
rect(slide, W * 0.62, 0, W * 0.38, H, fill=BG)

# 오른쪽 장식 써클들 (반투명 느낌)
for cx_, cy_, cr, alpha in [
    (W * 0.82, Inches(1.2), Inches(2.8), RGBColor(0x3D,0x5A,0xFE)),
    (W * 0.95, Inches(3.5), Inches(2.0), TEAL_L),
    (W * 0.68, Inches(5.8), Inches(1.5), INDIGO_L),
]:
    rect(slide, cx_ - cr/2, cy_ - cr/2, cr, cr, fill=alpha)

# 상단 인디고 선
rect(slide, 0, 0, W * 0.62, Inches(0.1), fill=TEAL)

# 로고 영역
rect(slide, Inches(0.6), Inches(1.4), Inches(0.6), Inches(2.8), fill=TEAL)
rect(slide, Inches(1.3), Inches(1.4), Inches(0.08), Inches(2.8),
     fill=RGBColor(0xFF,0xFF,0xFF))

# 메인 제목
tb(slide, "OpenAlio MCP",
   Inches(1.6), Inches(1.4), Inches(7.2), Inches(1.4),
   size=54, bold=True, color=WHITE)

# 부제
tb(slide, "공공기관 정보공개의 AI 활용성 제고를 위한",
   Inches(1.6), Inches(3.0), Inches(7.2), Inches(0.5),
   size=18, color=INDIGO_L)
tb(slide, "MCP 기반 실험",
   Inches(1.6), Inches(3.5), Inches(7.2), Inches(0.5),
   size=18, color=TEAL)

# 구분선
rect(slide, Inches(1.6), Inches(4.15), Inches(3.5), Inches(0.06), fill=AMBER)

# 발표자
tb(slide, "김보성 사무관",
   Inches(1.6), Inches(4.42), Inches(5), Inches(0.52),
   size=20, bold=True, color=WHITE)
tb(slide, "재경부 공공정책국    |    2026. 06.",
   Inches(1.6), Inches(4.95), Inches(6), Inches(0.4),
   size=14, color=INDIGO_L)

# 오른쪽 키워드 필
kws = [("🔗 연결", TEAL_L, TEAL_D), ("🤖 AI 활용", INDIGO_L, INDIGO_D),
       ("📊 공공데이터", MINT_L, RGBColor(0x00,0x69,0x2E))]
ky = Inches(2.0)
for kw, kfill, kcol in kws:
    pill(slide, kw, W * 0.67, ky, w=Inches(3.5), h=Inches(0.5),
         fill=kfill, color=kcol, size=15)
    ky += Inches(0.72)

# ════════════════════════════════════════════════════════════════
#  S01 – ALIO 성공 사례
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "01   공공기관 정보공개의 성공, ALIO",
            "ALIO는 공공기관 투명성 제고를 위한 대표적인 성공 사례")
footer(slide, 1)

# 왼쪽 카드
card(slide, Inches(0.35), Inches(1.35), Inches(5.8), Inches(5.7), INDIGO)
tb(slide, "ALIO의 핵심 성과",
   Inches(0.55), Inches(1.55), Inches(5.4), Inches(0.5),
   size=17, bold=True, color=INDIGO_D)

feats = [
    ("📢", "대국민 공개", "355개 공공기관 경영정보\n투명하게 공개"),
    ("🔍", "알권리 확대", "국민 누구나 무료로\n정보 열람 가능"),
    ("⚖️", "책임성 강화", "재무·인사·경영평가\n공시 의무화"),
    ("🌐", "서비스 확장", "ALIO PLUS, JOB-ALIO 등\n지속적 서비스 확장"),
]
fy = Inches(2.15)
for icon, ftitle, fdesc in feats:
    rect(slide, Inches(0.55), fy, Inches(5.4), Inches(1.0), fill=BG,
         line_color=INDIGO_L, line_w=Pt(0.5))
    tb(slide, icon, Inches(0.65), fy + Inches(0.1), Inches(0.6), Inches(0.8), size=22)
    tb(slide, ftitle, Inches(1.32), fy + Inches(0.08),
       Inches(4.5), Inches(0.35), size=14, bold=True, color=INDIGO_D)
    tb(slide, fdesc, Inches(1.32), fy + Inches(0.42),
       Inches(4.5), Inches(0.5), size=12, color=TXT_M)
    fy += Inches(1.12)

# 오른쪽 타임라인
card(slide, Inches(6.5), Inches(1.35), Inches(6.45), Inches(5.7), TEAL)
tb(slide, "서비스 발전 연혁",
   Inches(6.7), Inches(1.55), Inches(6.1), Inches(0.5),
   size=17, bold=True, color=TEAL_D)

timeline = [
    ("2005", "ALIO 출범", "공공기관 경영정보 최초 온라인 공개", INDIGO),
    ("2014", "ALIO PLUS", "채용·시설·사업 등 생활밀착 정보 통합", TEAL),
    ("2019", "JOB-ALIO", "공공기관 채용 전문 플랫폼 분리 출범", CORAL),
    ("2026", "OpenAlio MCP", "AI 활용 가능 개방형 인터페이스 실험", PURPLE),
]
ty = Inches(2.15)
for year, name, desc, col in timeline:
    rect(slide, Inches(6.7), ty, Inches(0.9), Inches(0.9), fill=col)
    tb(slide, year, Inches(6.7), ty + Inches(0.2), Inches(0.9), Inches(0.5),
       size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    rect(slide, Inches(7.75), ty + Inches(0.35),
         Inches(0.5), Inches(0.06), fill=col)
    tb(slide, name, Inches(8.35), ty + Inches(0.05),
       Inches(4.4), Inches(0.38), size=15, bold=True, color=col)
    tb(slide, desc, Inches(8.35), ty + Inches(0.44),
       Inches(4.4), Inches(0.35), size=12, color=TXT_M)
    if year != "2026":
        rect(slide, Inches(7.12), ty + Inches(0.9),
             Inches(0.06), Inches(0.22), fill=TXT_L)
    ty += Inches(1.15)

# ════════════════════════════════════════════════════════════════
#  S02 – AI 시대의 과제
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "02   그러나 AI 시대의 새로운 과제",
            "정보 공개는 성공했지만 정보 활용은 여전히 어렵다")
footer(slide, 2)

# 왼쪽 – 분산된 정보원
card(slide, Inches(0.35), Inches(1.35), Inches(5.8), Inches(5.7), CORAL)
tb(slide, "공공기관 정보, 어디에 흩어져 있나?",
   Inches(0.55), Inches(1.55), Inches(5.4), Inches(0.5),
   size=16, bold=True, color=CORAL)

src_items = [
    ("ALIO", "경영공시 정보", INDIGO, INDIGO_L),
    ("ALIO PLUS", "채용·시설·사업", TEAL_D, TEAL_L),
    ("JOB-ALIO", "채용 공고", CORAL, CORAL_L),
    ("기관 홈페이지", "기관별 자체 정보", PURPLE, PURPLE_L),
    ("법령 / 지침", "법적 근거·지침", MINT, MINT_L),
    ("뉴스 / 보도자료", "실시간 이슈", AMBER_D, RGBColor(0xFF,0xF3,0xCD)),
]
sy = Inches(2.1)
for name, desc, col, col_l in src_items:
    rect(slide, Inches(0.55), sy, Inches(5.4), Inches(0.68), fill=col_l,
         line_color=col, line_w=Pt(0.75))
    rect(slide, Inches(0.55), sy, Inches(0.12), Inches(0.68), fill=col)
    tb(slide, name, Inches(0.78), sy + Inches(0.06),
       Inches(2.0), Inches(0.35), size=13, bold=True, color=col)
    tb(slide, desc, Inches(2.85), sy + Inches(0.17),
       Inches(3.0), Inches(0.3), size=12, color=TXT_M)
    sy += Inches(0.78)

# 오른쪽 – 문제점
card(slide, Inches(6.5), Inches(1.35), Inches(6.45), Inches(5.7), INDIGO)
tb(slide, "AI가 활용하기 어려운 이유",
   Inches(6.7), Inches(1.55), Inches(6.1), Inches(0.5),
   size=16, bold=True, color=INDIGO_D)

problems = [
    ("🗂", "분  산", "정보가 여러 사이트에 나뉘어 있어\n통합 조회 불가", INDIGO),
    ("📄", "비구조", "PDF·엑셀·웹페이지 혼재로\nAI 파싱 어려움", CORAL),
    ("🔗", "비연결", "기관 간 연계 없어\n비교·분석 불가", TEAL_D),
    ("🤖", "저기계가독", "표준화된 API 없어\nAI 직접 활용 불가", PURPLE),
]
py = Inches(2.1)
for icon, ptitle, pdesc, col in problems:
    rect(slide, Inches(6.7), py, Inches(6.1), Inches(1.12), fill=BG,
         line_color=col, line_w=Pt(0.75))
    tb(slide, icon, Inches(6.8), py + Inches(0.2), Inches(0.55), Inches(0.7), size=24)
    tb(slide, ptitle, Inches(7.45), py + Inches(0.1),
       Inches(1.5), Inches(0.38), size=15, bold=True, color=col)
    tb(slide, pdesc, Inches(7.45), py + Inches(0.5),
       Inches(5.1), Inches(0.55), size=12, color=TXT_M)
    py += Inches(1.25)

tb(slide, "정보는 공개됐지만, AI는 아직 '읽지 못한다'",
   Inches(6.5), Inches(6.55), Inches(6.5), Inches(0.42),
   size=13, bold=True, color=CORAL, italic=True)

# ════════════════════════════════════════════════════════════════
#  S03 – 국민 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "03   국민 입장에서의 Pain Point",
            "정보는 공개되어 있으나 '질문하기' 어렵다")
footer(slide, 3)

# 질문 하이라이트
rect(slide, Inches(0.35), Inches(1.35), W - Inches(0.7), Inches(0.75), fill=INDIGO)
tb(slide, '💬   "한국전력의 최근 5년 부채 추이는?"',
   Inches(0.55), Inches(1.44), W - Inches(1.2), Inches(0.6),
   size=22, bold=True, color=WHITE)

# Before 카드
card(slide, Inches(0.35), Inches(2.25), Inches(5.9), Inches(4.82), CORAL)
tb(slide, "Before  ·  현재 절차",
   Inches(0.55), Inches(2.44), Inches(5.5), Inches(0.42),
   size=15, bold=True, color=CORAL)

before_steps = [
    ("①", "ALIO 접속"),
    ("②", "기관 검색"),
    ("③", "재무현황 이동"),
    ("④", "자료 다운로드"),
    ("⑤", "직접 분석"),
]
by2 = Inches(2.98)
for num, step in before_steps:
    rect(slide, Inches(0.55), by2, Inches(5.5), Inches(0.5),
         fill=CORAL_L, line_color=CORAL, line_w=Pt(0.5))
    tb(slide, num, Inches(0.62), by2 + Inches(0.07),
       Inches(0.42), Inches(0.38), size=14, bold=True, color=CORAL, align=PP_ALIGN.CENTER)
    tb(slide, step, Inches(1.1), by2 + Inches(0.07),
       Inches(4.8), Inches(0.38), size=14, color=TXT_D)
    if num != "⑤":
        arrow_v(slide, Inches(0.55) + Inches(5.5)/2, by2 + Inches(0.5), Inches(0.22))
    by2 += Inches(0.72)

tb(slide, "⏱  수십 분 ~ 수 시간 소요",
   Inches(0.55), Inches(6.6), Inches(5.5), Inches(0.38),
   size=13, bold=True, color=CORAL, italic=True)

# After 카드
card(slide, Inches(6.65), Inches(2.25), Inches(6.3), Inches(4.82), TEAL)
tb(slide, "After  ·  OpenAlio MCP 활용",
   Inches(6.85), Inches(2.44), Inches(5.9), Inches(0.42),
   size=15, bold=True, color=TEAL_D)

after_steps = [
    ("💬", "질문 입력", "자연어로 자유롭게"),
    ("🤖", "AI + MCP", "32개 도구 자동 선택"),
    ("📊", "즉시 결과", "표·그래프·출처 포함"),
]
ay = Inches(2.98)
for icon, step, desc in after_steps:
    rect(slide, Inches(6.85), ay, Inches(5.9), Inches(0.9),
         fill=TEAL_L, line_color=TEAL, line_w=Pt(0.5))
    tb(slide, icon, Inches(6.95), ay + Inches(0.15), Inches(0.55), Inches(0.6), size=22)
    tb(slide, step, Inches(7.6), ay + Inches(0.08),
       Inches(4.9), Inches(0.35), size=14, bold=True, color=TEAL_D)
    tb(slide, desc, Inches(7.6), ay + Inches(0.48),
       Inches(4.9), Inches(0.3), size=12, color=TXT_M)
    if icon != "📊":
        arrow_v(slide, Inches(6.85) + Inches(5.9)/2, ay + Inches(0.9), Inches(0.22))
    ay += Inches(1.12)

pill(slide, "⚡  수 초 이내 완료", Inches(6.85), Inches(6.55),
     w=Inches(3.5), h=Inches(0.38), fill=MINT_L,
     color=RGBColor(0x00,0x69,0x2E), size=13)

# ════════════════════════════════════════════════════════════════
#  S04 – 공공기관 실무자 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "04   공공기관 실무자 입장에서의 Pain Point",
            "벤치마킹과 업무학습 비용이 높다")
footer(slide, 4)

inst_pain = [
    ("🔍", "유사기관 운영사례 탐색",
     "동종 기관 운영사례를 여러 사이트에서\n수작업으로 수집해야 함",
     INDIGO, INDIGO_L),
    ("📝", "경영평가 대응사례 확인",
     "지적사항·우수사례 PDF를 연도별로\n일일이 찾아서 검토해야 함",
     TEAL_D, TEAL_L),
    ("📚", "신규 담당자 업무학습",
     "법령·지침·편람이 분산돼\n온보딩 비용 과다",
     CORAL, CORAL_L),
]
cx = Inches(0.35)
for icon, title, desc, col, col_l in inst_pain:
    card(slide, cx, Inches(1.35), Inches(4.15), Inches(5.3), col)
    tb(slide, icon, cx + Inches(0.2), Inches(1.6), Inches(0.8), Inches(0.8), size=30)
    tb(slide, title, cx + Inches(0.2), Inches(2.45),
       Inches(3.7), Inches(0.5), size=16, bold=True, color=col)
    rect(slide, cx + Inches(0.2), Inches(2.98),
         Inches(3.0), Inches(0.05), fill=col)
    tb(slide, desc, cx + Inches(0.2), Inches(3.12),
       Inches(3.7), Inches(1.5), size=14, color=TXT_M)

    # MCP 활용 힌트
    rect(slide, cx + Inches(0.2), Inches(5.4),
         Inches(3.7), Inches(0.88), fill=col_l,
         line_color=col, line_w=Pt(0.5))
    tb(slide, "→  MCP 활용 시",
       cx + Inches(0.32), Inches(5.47),
       Inches(3.5), Inches(0.3), size=11, bold=True, color=col)
    hints = {
        "유사기관 운영사례 탐색": "AI에게 물어보면 즉시 정리된\n벤치마킹 결과 제공",
        "경영평가 대응사례 확인": "편람 키워드 검색 + 연도별\n지적 패턴 즉시 분석",
        "신규 담당자 업무학습": "법령·지침 통합 검색으로\n온보딩 시간 대폭 단축",
    }
    tb(slide, hints[title], cx + Inches(0.32), Inches(5.77),
       Inches(3.5), Inches(0.5), size=11, color=TXT_D)
    cx += Inches(4.42)

rect(slide, Inches(0.35), Inches(6.78), W - Inches(0.7), Inches(0.42), fill=INDIGO)
tb(slide, "OpenAlio MCP가 3가지 Pain Point를 단번에 해결합니다",
   Inches(0.55), Inches(6.82), W - Inches(1.1), Inches(0.35),
   size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  S05 – 재경부 공무원 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "05   재경부·주무부처 공무원 입장에서의 Pain Point",
            "공개된 데이터를 활용하는 데 막대한 행정비용이 발생")
footer(slide, 5)

# 왼쪽 – 업무 유형
card(slide, Inches(0.35), Inches(1.35), Inches(4.1), Inches(5.7), PURPLE)
tb(slide, "주요 업무 유형",
   Inches(0.55), Inches(1.55), Inches(3.8), Inches(0.45),
   size=15, bold=True, color=PURPLE)

task_items = [
    ("⚙️", "기능개혁"), ("👥", "증원심사"),
    ("🏆", "경영평가"), ("🔀", "기관통합검토"),
    ("📰", "보도대응"), ("✅", "팩트체크"),
]
ty2 = Inches(2.1)
for i, (ic, tn) in enumerate(task_items):
    rx2 = Inches(0.55) if i % 2 == 0 else Inches(2.3)
    if i % 2 == 0 and i > 0:
        ty2 += Inches(0.72)
    rect(slide, rx2, ty2, Inches(1.6), Inches(0.58),
         fill=PURPLE_L, line_color=PURPLE, line_w=Pt(0.5))
    tb(slide, f"{ic} {tn}", rx2 + Inches(0.05), ty2 + Inches(0.09),
       Inches(1.5), Inches(0.42), size=13, bold=True, color=PURPLE,
       align=PP_ALIGN.CENTER)
if len(task_items) % 2 == 0:
    ty2 += Inches(0.72)

# 오른쪽 – 업무 흐름
card(slide, Inches(4.75), Inches(1.35), Inches(8.2), Inches(5.7), CORAL)
tb(slide, "실제 업무 흐름 (현재)",
   Inches(4.95), Inches(1.55), Inches(7.8), Inches(0.45),
   size=15, bold=True, color=CORAL)

flow_items = [
    ("기관별 정원·재무·사업 정보 필요", INDIGO_L, TXT_D),
    ("ALIO 접속 → 항목별 클릭", CORAL_L, CORAL),
    ("엑셀 파일 수십 개 다운로드  ⚠️", CORAL_L, CORAL),
    ("수작업 정리·가공", CORAL_L, CORAL),
    ("분석 수행", INDIGO_L, TXT_D),
    ("보고서 작성", INDIGO_L, TXT_D),
]
fy2 = Inches(2.1)
for label, bg_c, txt_c in flow_items:
    rect(slide, Inches(4.95), fy2, Inches(7.8), Inches(0.5),
         fill=bg_c, line_color=TXT_L, line_w=Pt(0.3))
    tb(slide, label, Inches(5.05), fy2 + Inches(0.08),
       Inches(7.6), Inches(0.35), size=13, bold=(txt_c==CORAL), color=txt_c)
    if label != "보고서 작성":
        arrow_v(slide, Inches(4.95) + Inches(7.8)/2, fy2 + Inches(0.5), Inches(0.16))
    fy2 += Inches(0.68)

tb(slide, "⚠  기관 1개당 수십 개 파일  ×  355개 기관 = 막대한 행정비용",
   Inches(4.95), Inches(6.58), Inches(7.8), Inches(0.38),
   size=12, bold=True, color=CORAL, italic=True)

# ════════════════════════════════════════════════════════════════
#  S06 – 연구자 Pain Point
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "06   연구자 입장에서의 Pain Point",
            "데이터보다 데이터 준비에 더 많은 시간이 소요")
footer(slide, 6)

tb(slide, "연구 시간의 대부분이 데이터 준비에 소요됩니다",
   Inches(1.5), Inches(1.42), Inches(10), Inches(0.5),
   size=19, bold=True, color=TXT_D, align=PP_ALIGN.CENTER)

cycle = [
    ("📥", "수  집", "ALIO·기관 홈페이지\n수작업 다운로드", INDIGO, INDIGO_L),
    ("🧹", "정  제", "이상값·결측값\n수동 처리", CORAL, CORAL_L),
    ("🔗", "통  합", "기관 코드 통일\n형식 표준화", TEAL_D, TEAL_L),
    ("⚙️", "전처리", "분석 가능한\n형태로 변환", PURPLE, PURPLE_L),
]
cx4 = Inches(0.45)
for icon, ctitle, cdesc, col, col_l in cycle:
    card(slide, cx4, Inches(2.1), Inches(2.95), Inches(3.2), col, Inches(0.08))
    tb(slide, icon, cx4, Inches(2.28), Inches(2.95), Inches(0.8),
       size=32, align=PP_ALIGN.CENTER)
    tb(slide, ctitle, cx4, Inches(3.15), Inches(2.95), Inches(0.5),
       size=20, bold=True, color=col, align=PP_ALIGN.CENTER)
    rect(slide, cx4 + Inches(0.9), Inches(3.7),
         Inches(1.15), Inches(0.05), fill=col)
    tb(slide, cdesc, cx4 + Inches(0.1), Inches(3.85),
       Inches(2.75), Inches(0.9), size=13, color=TXT_M, align=PP_ALIGN.CENTER)
    # 화살표 (마지막 제외)
    if ctitle != "전처리":
        rect(slide, cx4 + Inches(2.95), Inches(3.5),
             Inches(0.4), Inches(0.08), fill=TXT_L)
    cx4 += Inches(3.35)

# 반복 루프 표시
tb(slide, "⟳  위 과정을 매 연구마다, 연구자마다 반복 수행",
   Inches(1.5), Inches(5.5), Inches(10), Inches(0.45),
   size=16, bold=True, color=TXT_M, align=PP_ALIGN.CENTER)

rect(slide, Inches(0.35), Inches(6.15), W - Inches(0.7), Inches(0.82), fill=INDIGO)
tb(slide, "OpenAlio MCP 활용 시  →  355개 기관 × 11개 메트릭 × 6년치 데이터를 즉시 제공",
   Inches(0.55), Inches(6.22), W - Inches(1.1), Inches(0.38),
   size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
tb(slide, "출처·공시일·단위까지 자동 첨부 — 데이터 준비 시간 90% 단축",
   Inches(0.55), Inches(6.6), W - Inches(1.1), Inches(0.32),
   size=12, color=INDIGO_L, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  S07 – OpenAlio MCP 개발
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "07   그래서 OpenAlio MCP를 개발",
            "공공기관 정보를 AI가 활용할 수 있도록 연결하는 개방형 인터페이스")
footer(slide, 7)

# 중앙 아키텍처
# 데이터 소스 레이어
tb(slide, "[ 데이터 소스 ]",
   Inches(0.35), Inches(1.42), Inches(4.0), Inches(0.4),
   size=13, bold=True, color=TXT_M)
data_srcs2 = [
    ("ALIO", INDIGO, INDIGO_L),
    ("ALIO PLUS", TEAL_D, TEAL_L),
    ("JOB-ALIO", CORAL, CORAL_L),
    ("법령·지침", PURPLE, PURPLE_L),
    ("편람", MINT, MINT_L),
    ("뉴스", AMBER_D, RGBColor(0xFF,0xF3,0xCD)),
]
dx3 = Inches(0.35)
for ds, col, col_l in data_srcs2:
    rect(slide, dx3, Inches(1.88), Inches(1.85), Inches(0.6),
         fill=col_l, line_color=col, line_w=Pt(0.75))
    tb(slide, ds, dx3, Inches(1.9), Inches(1.85), Inches(0.58),
       size=13, bold=True, color=col, align=PP_ALIGN.CENTER)
    dx3 += Inches(1.98)

# 화살표 아래
for xi in [Inches(2.2), Inches(4.2), Inches(6.2),
           Inches(8.2), Inches(10.2), Inches(12.2)]:
    rect(slide, xi, Inches(2.48), Inches(0.06), Inches(0.35), fill=TXT_L)

# MCP 박스 (핵심)
rect(slide, Inches(1.5), Inches(2.83), Inches(10.2), Inches(1.35), fill=INDIGO)
rect(slide, Inches(1.5), Inches(2.83), Inches(10.2), Inches(0.08), fill=AMBER)
tb(slide, "OpenAlio MCP",
   Inches(1.5), Inches(2.93), Inches(10.2), Inches(0.62),
   size=28, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
tb(slide, "32개 도구  ·  2개 프롬프트  ·  5개 리소스  ·  355개 기관  ·  11개 메트릭  ·  6년치 데이터",
   Inches(1.5), Inches(3.55), Inches(10.2), Inches(0.55),
   size=13, color=INDIGO_L, align=PP_ALIGN.CENTER)

# 화살표 아래
for xi2 in [Inches(3.0), Inches(5.5), Inches(8.0), Inches(10.5)]:
    rect(slide, xi2, Inches(4.18), Inches(0.06), Inches(0.35), fill=TXT_L)

# 활용 대상
tb(slide, "[ 활용 대상 ]",
   Inches(1.5), Inches(4.52), Inches(4.0), Inches(0.4),
   size=13, bold=True, color=TXT_M)
users2 = [
    ("👨‍👩‍👧", "국민", "정보 조회·질문", INDIGO, INDIGO_L),
    ("🏢", "공공기관", "벤치마킹·학습", TEAL_D, TEAL_L),
    ("💼", "공무원", "업무 자동화", CORAL, CORAL_L),
    ("🔬", "연구자", "데이터 분석", PURPLE, PURPLE_L),
]
ux = Inches(1.5)
for uicon, uname, udesc, ucol, ucol_l in users2:
    rect(slide, ux, Inches(4.92), Inches(2.4), Inches(1.5),
         fill=ucol_l, line_color=ucol, line_w=Pt(0.75))
    tb(slide, uicon, ux, Inches(5.0), Inches(2.4), Inches(0.7),
       size=22, align=PP_ALIGN.CENTER)
    tb(slide, uname, ux, Inches(5.72), Inches(2.4), Inches(0.45),
       size=14, bold=True, color=ucol, align=PP_ALIGN.CENTER)
    tb(slide, udesc, ux, Inches(6.18), Inches(2.4), Inches(0.3),
       size=11, color=TXT_M, align=PP_ALIGN.CENTER)
    ux += Inches(2.58)

# 핵심 문구
rect(slide, Inches(0.35), Inches(6.78), W - Inches(0.7), Inches(0.42), fill=AMBER)
tb(slide, "공공기관 정보를 AI가 활용 가능한 형태로 연결하는 개방형 인터페이스",
   Inches(0.55), Inches(6.82), W - Inches(1.1), Inches(0.35),
   size=15, bold=True, color=TXT_D, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  S08 – MCP란?
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "08   MCP란 무엇인가",
            "MCP = Model Context Protocol  ·  AI 시대의 USB-C")
footer(slide, 8)

# 왼쪽 – USB 비유
card(slide, Inches(0.35), Inches(1.35), Inches(5.9), Inches(5.7), CORAL)
tb(slide, "USB-C 비유로 이해하기",
   Inches(0.55), Inches(1.55), Inches(5.6), Inches(0.45),
   size=16, bold=True, color=CORAL)

# Before
tb(slide, "Before  ·  기기마다 다른 충전기",
   Inches(0.55), Inches(2.08), Inches(5.6), Inches(0.38),
   size=13, bold=True, color=TXT_M)
old_devices = ["스마트폰", "태블릿", "노트북", "카메라"]
ox3 = Inches(0.6)
for od in old_devices:
    rect(slide, ox3, Inches(2.55), Inches(1.1), Inches(0.45),
         fill=CORAL_L, line_color=CORAL, line_w=Pt(0.5))
    tb(slide, od, ox3, Inches(2.57), Inches(1.1), Inches(0.4),
       size=11, color=CORAL, align=PP_ALIGN.CENTER)
    rect(slide, ox3 + Inches(1.1), Inches(2.7),
         Inches(0.25), Inches(0.08), fill=CORAL)
    rect(slide, ox3 + Inches(1.35), Inches(2.55), Inches(0.18), Inches(0.45),
         fill=CORAL)
    ox3 += Inches(1.3)

# After
tb(slide, "After  ·  USB-C 하나로 통일",
   Inches(0.55), Inches(3.28), Inches(5.6), Inches(0.38),
   size=13, bold=True, color=TEAL_D)
new_devices = ["스마트폰", "태블릿", "노트북", "카메라"]
nx = Inches(0.6)
for nd in new_devices:
    rect(slide, nx, Inches(3.75), Inches(1.1), Inches(0.45),
         fill=TEAL_L, line_color=TEAL_D, line_w=Pt(0.5))
    tb(slide, nd, nx, Inches(3.77), Inches(1.1), Inches(0.4),
       size=11, color=TEAL_D, align=PP_ALIGN.CENTER)
    rect(slide, nx + Inches(0.52), Inches(4.2),
         Inches(0.06), Inches(0.28), fill=TEAL_D)
    nx += Inches(1.3)
rect(slide, Inches(0.85), Inches(4.48),
     Inches(5.2), Inches(0.06), fill=TEAL_D)
rect(slide, Inches(3.2), Inches(4.54),
     Inches(0.06), Inches(0.3), fill=TEAL_D)
rect(slide, Inches(2.85), Inches(4.84),
     Inches(0.75), Inches(0.42), fill=TEAL_D)
tb(slide, "USB-C", Inches(2.85), Inches(4.86), Inches(0.75), Inches(0.38),
   size=12, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# 오른쪽 – MCP 설명
card(slide, Inches(6.6), Inches(1.35), Inches(6.35), Inches(5.7), INDIGO)
tb(slide, "MCP = Model Context Protocol",
   Inches(6.8), Inches(1.55), Inches(6.0), Inches(0.45),
   size=16, bold=True, color=INDIGO_D)

tb(slide, "AI 모델이 다양한 외부 데이터·도구와\n표준화된 방식으로 연결하는 프로토콜",
   Inches(6.8), Inches(2.1), Inches(6.0), Inches(0.75),
   size=14, color=TXT_D)

mcp_feats = [
    ("🔌", "표준화", "어떤 AI든 동일한 방식으로 연결"),
    ("🔒", "안전성", "입력 검증·응답 크기 제한 내장"),
    ("📦", "모듈성", "도구 단위로 독립 추가·제거 가능"),
    ("🚀", "확장성", "새 데이터소스 연결 용이"),
]
mf_y = Inches(3.0)
for icon, mtitle, mdesc in mcp_feats:
    rect(slide, Inches(6.8), mf_y, Inches(5.9), Inches(0.68),
         fill=BG, line_color=INDIGO_L, line_w=Pt(0.5))
    tb(slide, icon, Inches(6.9), mf_y + Inches(0.1),
       Inches(0.55), Inches(0.5), size=18)
    tb(slide, mtitle, Inches(7.55), mf_y + Inches(0.07),
       Inches(1.3), Inches(0.35), size=13, bold=True, color=INDIGO_D)
    tb(slide, mdesc, Inches(8.95), mf_y + Inches(0.17),
       Inches(3.6), Inches(0.38), size=12, color=TXT_M)
    mf_y += Inches(0.8)

tb(slide, "Claude / ChatGPT / Cursor / 브리티웍스 · · ·",
   Inches(6.8), Inches(6.38), Inches(6.0), Inches(0.38),
   size=13, color=INDIGO, italic=True, bold=True)

# ════════════════════════════════════════════════════════════════
#  S09 – 동작 원리
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "09   OpenAlio MCP는 어떻게 동작하는가",
            "질문 한 번으로 공공기관 데이터 분석·보고서까지")
footer(slide, 9)

# 중앙 플로우
flow_labels2 = [
    ("💬  사용자 질문", INDIGO),
    ("🤖  AI  (Claude / ChatGPT 등)", INDIGO),
    ("⚙️  OpenAlio MCP  (32개 도구)", AMBER_D),
    ("🗄  ALIO · ALIO PLUS · 법령 · 뉴스 조회", TEAL_D),
    ("📈  분석 수행", TEAL),
    ("📋  표 · 그래프 · 보고서 + 출처 자동 첨부", MINT),
]
bw2 = Inches(5.0)
bh2 = Inches(0.6)
gp2 = Inches(0.22)
sx = (W - bw2) / 2
sy2 = Inches(1.42)

for i, (lbl, col) in enumerate(flow_labels2):
    by3 = sy2 + i * (bh2 + gp2)
    rect(slide, sx, by3, bw2, bh2, fill=col)
    tb(slide, lbl, sx + Inches(0.1), by3 + Pt(4), bw2 - Inches(0.2), bh2,
       size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    if i < len(flow_labels2) - 1:
        arrow_v(slide, sx + bw2/2, by3 + bh2, gp2)

# 왼쪽 예시 질문
card(slide, Inches(0.35), Inches(1.35), Inches(3.35), Inches(5.7), INDIGO)
tb(slide, "예시 질문",
   Inches(0.55), Inches(1.55), Inches(3.1), Inches(0.42),
   size=14, bold=True, color=INDIGO_D)

qs = [
    "\"최근 5년 부채 증가율\n상위 10개 기관\"",
    "\"A기관·B기관 통합\n검토 보고서\"",
    "\"육아휴직 사용률 가장\n높은 기관은?\"",
]
qy2 = Inches(2.08)
for q in qs:
    rect(slide, Inches(0.55), qy2, Inches(3.0), Inches(1.22),
         fill=INDIGO_L, line_color=INDIGO, line_w=Pt(0.5))
    tb(slide, q, Inches(0.65), qy2 + Inches(0.15),
       Inches(2.8), Inches(0.95), size=13, color=INDIGO_D, italic=True)
    qy2 += Inches(1.4)

# 오른쪽 출력 예시
card(slide, Inches(9.65), Inches(1.35), Inches(3.35), Inches(5.7), MINT)
tb(slide, "출력 형태",
   Inches(9.85), Inches(1.55), Inches(3.1), Inches(0.42),
   size=14, bold=True, color=RGBColor(0x00,0x69,0x2E))

outputs2 = [
    ("📊", "시계열 차트"),
    ("📋", "비교 표"),
    ("📝", "보고서 초안"),
    ("🔗", "출처 및 공시일"),
    ("⚠️", "결측 사유 안내"),
]
oy4 = Inches(2.08)
for icon, otxt in outputs2:
    rect(slide, Inches(9.85), oy4, Inches(3.0), Inches(0.75),
         fill=MINT_L, line_color=MINT, line_w=Pt(0.5))
    tb(slide, icon, Inches(9.95), oy4 + Inches(0.1),
       Inches(0.5), Inches(0.55), size=18)
    tb(slide, otxt, Inches(10.55), oy4 + Inches(0.2),
       Inches(2.2), Inches(0.38), size=13, color=TXT_D, bold=True)
    oy4 += Inches(0.9)

# ════════════════════════════════════════════════════════════════
#  S10 – 활용 사례 ① 국민
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "10   활용 사례 ①  국민 서비스",
            "누구나 AI에게 물어보면 공공기관 정보를 즉시 확인")
footer(slide, 10)

citizen = [
    ("💰", "한전 부채 얼마야?",
     "한국전력 최근 5년 부채 추이\n수치·그래프 즉시 제공",
     INDIGO, INDIGO_L),
    ("👶", "육아휴직 사용률이\n가장 높은 기관은?",
     "355개 기관 육아휴직 데이터\n순위 표 자동 생성",
     TEAL_D, TEAL_L),
    ("🏟️", "근처 공공기관\n체육시설 알려줘",
     "ALIO PLUS 시설 정보\n예약 링크·운영시간 안내",
     CORAL, CORAL_L),
]
cx5 = Inches(0.35)
for icon, q, result, col, col_l in citizen:
    card(slide, cx5, Inches(1.35), Inches(4.1), Inches(5.72), col)
    tb(slide, icon, cx5, Inches(1.6), Inches(4.1), Inches(0.9),
       size=40, align=PP_ALIGN.CENTER)
    # 질문 버블
    rect(slide, cx5 + Inches(0.15), Inches(2.62),
         Inches(3.8), Inches(1.12), fill=col_l,
         line_color=col, line_w=Pt(0.75))
    tb(slide, q, cx5 + Inches(0.25), Inches(2.75),
       Inches(3.6), Inches(0.9), size=16, bold=True, color=col,
       align=PP_ALIGN.CENTER)
    # 구분선
    rect(slide, cx5 + Inches(0.5), Inches(3.85),
         Inches(3.1), Inches(0.05), fill=col)
    tb(slide, "→ 결과", cx5 + Inches(0.25), Inches(4.0),
       Inches(3.6), Inches(0.4), size=13, bold=True, color=col)
    tb(slide, result, cx5 + Inches(0.25), Inches(4.42),
       Inches(3.6), Inches(1.0), size=14, color=TXT_M)
    cx5 += Inches(4.42)

rect(slide, Inches(0.35), Inches(7.22), W - Inches(0.7), Inches(0.42), fill=TEAL_D)
tb(slide, "사용자는 웹사이트 구조를 몰라도 됩니다  —  질문만 하면 됩니다",
   Inches(0.55), Inches(7.26), W - Inches(1.1), Inches(0.35),
   size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  S11 – 활용 사례 ② 공공기관 실무자
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "11   활용 사례 ②  공공기관 실무자",
            "벤치마킹·평가 대응·조직운영 정보를 즉시 활용")
footer(slide, 11)

inst_use = [
    ("📊", "ESG 우수사례 정리",
     '"유사기관 ESG 우수사례 정리"',
     "동종 기관 ESG 공시 항목\n우수 사례 자동 요약 제공",
     INDIGO, INDIGO_L),
    ("🏆", "경영평가 지적사항",
     '"최근 경영평가 지적사항 분석"',
     "2025·2026 평가편람 기준\n지적 패턴·주요 지표 분석",
     TEAL_D, TEAL_L),
    ("👥", "조직운영 비교",
     '"기관별 조직운영 비교"',
     "정원·실인원·보수 등\n11개 메트릭 동시 비교",
     CORAL, CORAL_L),
]
ix2 = Inches(0.35)
for icon, title, q, result, col, col_l in inst_use:
    card(slide, ix2, Inches(1.35), Inches(4.1), Inches(5.72), col)
    tb(slide, icon, ix2, Inches(1.6), Inches(4.1), Inches(0.9),
       size=38, align=PP_ALIGN.CENTER)
    tb(slide, title, ix2 + Inches(0.15), Inches(2.52),
       Inches(3.8), Inches(0.48), size=16, bold=True, color=col,
       align=PP_ALIGN.CENTER)
    # 질문
    rect(slide, ix2 + Inches(0.15), Inches(3.1),
         Inches(3.8), Inches(0.75), fill=col_l,
         line_color=col, line_w=Pt(0.5))
    tb(slide, q, ix2 + Inches(0.25), Inches(3.22),
       Inches(3.6), Inches(0.55), size=13, color=col, italic=True,
       align=PP_ALIGN.CENTER)
    rect(slide, ix2 + Inches(0.5), Inches(3.95),
         Inches(3.1), Inches(0.05), fill=col)
    tb(slide, "출력 결과", ix2 + Inches(0.25), Inches(4.08),
       Inches(3.6), Inches(0.35), size=12, bold=True, color=col)
    tb(slide, result, ix2 + Inches(0.25), Inches(4.45),
       Inches(3.6), Inches(1.0), size=14, color=TXT_M)
    ix2 += Inches(4.42)

rect(slide, Inches(0.35), Inches(7.22), W - Inches(0.7), Inches(0.42), fill=TEAL_D)
tb(slide, "법령·지침·편람 통합 검색  —  신규 담당자 온보딩 시간 대폭 단축",
   Inches(0.55), Inches(7.26), W - Inches(1.1), Inches(0.35),
   size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  S12 – 활용 사례 ③ 재경부 (★ 핵심)
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "12   활용 사례 ③  재경부 업무  ★  (핵심 슬라이드)",
            "기관 통합 검토 보고서를 AI가 자동으로 작성")
footer(slide, 12)

# 질문 강조 배너
rect(slide, Inches(0.35), Inches(1.35), W - Inches(0.7), Inches(0.82), fill=INDIGO_D)
rect(slide, Inches(0.35), Inches(1.35), Inches(0.12), Inches(0.82), fill=AMBER)
tb(slide, '💬  "A기관과 B기관 통합 검토 보고서 작성해 줘"',
   Inches(0.62), Inches(1.46), W - Inches(1.2), Inches(0.62),
   size=22, bold=True, color=WHITE)

# 출력 항목 카드들
output_cards = [
    ("📊", "재무현황", "부채·자산·수익\n최근 5년 추이", INDIGO),
    ("👥", "인력현황", "정원·실인원·신규\n채용 현황", TEAL_D),
    ("🏢", "주요사업", "설립 목적·핵심\n기능 정리", PURPLE),
    ("📍", "지역분포", "본사·지사 소재지\n지역별 인력", CORAL),
    ("🔀", "중복기능", "유사 기능 도출\n통합 시 효율", MINT),
    ("🎯", "기대효과", "시나리오별\n예상 효과 요약", AMBER_D),
]
ox4 = Inches(0.35)
oy5 = Inches(2.35)
for i, (icon, title, desc, col) in enumerate(output_cards):
    if i == 3:
        ox4 = Inches(0.35)
        oy5 = Inches(4.2)
    card(slide, ox4, oy5, Inches(2.05), Inches(1.65), col)
    tb(slide, icon, ox4, oy5 + Inches(0.16),
       Inches(2.05), Inches(0.5), size=22, align=PP_ALIGN.CENTER)
    tb(slide, title, ox4, oy5 + Inches(0.7),
       Inches(2.05), Inches(0.38), size=14, bold=True, color=col,
       align=PP_ALIGN.CENTER)
    tb(slide, desc, ox4 + Inches(0.08), oy5 + Inches(1.08),
       Inches(1.9), Inches(0.5), size=11, color=TXT_M,
       align=PP_ALIGN.CENTER)
    ox4 += Inches(2.22)

# 오른쪽 기대효과
card(slide, Inches(7.0), Inches(2.28), Inches(5.95), Inches(3.65), AMBER_D)
tb(slide, "기대 효과",
   Inches(7.2), Inches(2.48), Inches(5.7), Inches(0.45),
   size=16, bold=True, color=AMBER_D)

effects2 = [
    ("⏱", "수 시간 → 수 분으로 보고서 작성 시간 단축"),
    ("📁", "수작업 엑셀 없이 자동 데이터 수집·정리"),
    ("🔗", "출처 자동 첨부 (공시일·API 기록 포함)"),
    ("♻️", "증원심사·기능개혁 등 다양한 업무 재활용"),
]
ey2 = Inches(3.05)
for eicon, etxt in effects2:
    rect(slide, Inches(7.2), ey2, Inches(5.6), Inches(0.55),
         fill=RGBColor(0xFF,0xF8,0xE1), line_color=AMBER, line_w=Pt(0.5))
    tb(slide, eicon, Inches(7.28), ey2 + Inches(0.08),
       Inches(0.45), Inches(0.42), size=16)
    tb(slide, etxt, Inches(7.82), ey2 + Inches(0.1),
       Inches(4.85), Inches(0.38), size=13, color=TXT_D)
    ey2 += Inches(0.68)

rect(slide, Inches(0.35), Inches(6.78), W - Inches(0.7), Inches(0.42), fill=AMBER)
tb(slide, "공개된 데이터  +  AI  =  행정 생산성의 획기적 향상",
   Inches(0.55), Inches(6.82), W - Inches(1.1), Inches(0.35),
   size=16, bold=True, color=TXT_D, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════
#  S13 – 브리티웍스 연계
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "13   활용 사례 ④  브리티웍스 및 지능형 업무시스템",
            "OpenAlio MCP는 특정 AI 서비스가 아닌 기반 인프라")
footer(slide, 13)

tb(slide, "어떤 AI 시스템에도 연결 가능한 개방형 인터페이스",
   Inches(1.5), Inches(1.42), Inches(10), Inches(0.5),
   size=20, bold=True, color=TXT_D, align=PP_ALIGN.CENTER)

# AI 서비스 레이어
ai_services = [
    ("💼", "브리티웍스", INDIGO, INDIGO_L),
    ("⚙️", "지능형 업무시스템", PURPLE, PURPLE_L),
    ("🤖", "Claude / ChatGPT", TEAL_D, TEAL_L),
    ("🔮", "향후 AI 플랫폼", CORAL, CORAL_L),
]
ax3 = Inches(0.4)
for aicon, aname, acol, acol_l in ai_services:
    rect(slide, ax3, Inches(2.05), Inches(2.85), Inches(1.0),
         fill=acol_l, line_color=acol, line_w=Pt(0.75))
    tb(slide, aicon, ax3, Inches(2.1), Inches(2.85), Inches(0.55),
       size=24, align=PP_ALIGN.CENTER)
    tb(slide, aname, ax3, Inches(2.68), Inches(2.85), Inches(0.3),
       size=13, bold=True, color=acol, align=PP_ALIGN.CENTER)
    # 연결선 아래
    rect(slide, ax3 + Inches(1.35), Inches(3.05),
         Inches(0.06), Inches(0.38), fill=TXT_L)
    ax3 += Inches(3.1)

# MCP 핵심 박스
rect(slide, Inches(2.2), Inches(3.43), Inches(8.9), Inches(1.12), fill=INDIGO)
rect(slide, Inches(2.2), Inches(3.43), Inches(8.9), Inches(0.1), fill=AMBER)
rect(slide, Inches(2.2), Inches(4.45), Inches(8.9), Inches(0.1), fill=AMBER)
tb(slide, "OpenAlio MCP  —  표준 인터페이스 (MCP 프로토콜)",
   Inches(2.2), Inches(3.6), Inches(8.9), Inches(0.55),
   size=22, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
tb(slide, "표준화된 방식으로 어떤 AI든 연결 · 재사용 가능",
   Inches(2.2), Inches(4.12), Inches(8.9), Inches(0.32),
   size=13, color=INDIGO_L, align=PP_ALIGN.CENTER)

# 연결선 아래
rect(slide, W/2 - Inches(0.04), Inches(4.55),
     Inches(0.08), Inches(0.38), fill=TXT_L)

# 데이터 소스 레이어
data_layer = [
    ("ALIO", INDIGO, INDIGO_L),
    ("ALIO PLUS", TEAL_D, TEAL_L),
    ("JOB-ALIO", CORAL, CORAL_L),
    ("법령 / 지침", PURPLE, PURPLE_L),
]
dx4 = Inches(1.2)
for dname, dcol, dcol_l in data_layer:
    rect(slide, dx4, Inches(4.93), Inches(2.55), Inches(0.65),
         fill=dcol_l, line_color=dcol, line_w=Pt(0.75))
    tb(slide, dname, dx4, Inches(4.95), Inches(2.55), Inches(0.6),
       size=14, bold=True, color=dcol, align=PP_ALIGN.CENTER)
    dx4 += Inches(2.8)

# 설명 포인트
rect(slide, Inches(0.35), Inches(5.82), W - Inches(0.7), Inches(0.95), fill=WHITE,
     line_color=INDIGO_L, line_w=Pt(0.5))
pts2 = [
    "표준화된 MCP 프로토콜로 브리티웍스·지능형 업무시스템에 바로 연결 가능",
    "새로운 AI 플랫폼 도입 시에도 OpenAlio MCP는 그대로 재사용  —  인프라 투자 보호",
    "향후 데이터 추가(평가결과·국회·조달)도 MCP 서버에만 반영하면 모든 AI에 즉시 적용",
]
py3 = Inches(5.9)
for pt in pts2:
    tb(slide, f"•  {pt}", Inches(0.55), py3, W - Inches(1.1), Inches(0.28),
       size=13, color=TXT_D)
    py3 += Inches(0.28)

# ════════════════════════════════════════════════════════════════
#  S14 – 향후 발전 방향
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)
slide_bg(slide)
header_band(slide, "14   향후 발전 방향",
            "단계적 확장으로 공공기관 정보공개 체계를 AI 시대에 맞게 고도화")
footer(slide, 14)

roadmap2 = [
    ("대국민 서비스", "🌐", INDIGO, INDIGO_L, [
        "ALIO 챗봇 구현",
        "기관 비교 서비스",
        "정책 팩트체크",
    ]),
    ("내부 업무 지원", "💼", CORAL, CORAL_L, [
        "증원심사 지원",
        "기능개혁 지원",
        "경영평가 지원",
        "언론대응·기관현황 자동 작성",
    ]),
    ("연구 활용", "🔬", TEAL_D, TEAL_L, [
        "공공기관 데이터 분석 플랫폼",
        "평가결과 데이터 추가",
        "국회·조달 데이터 연계",
    ]),
    ("인프라 고도화", "🛠", PURPLE, PURPLE_L, [
        "HTTP/SSE 서버 전환",
        "인증·속도 제한 적용",
        "자동 업데이트 파이프라인",
        "보안 심의 대응",
    ]),
]
rx2 = Inches(0.35)
for rname, ricon, rcol, rcol_l, ritems in roadmap2:
    card(slide, rx2, Inches(1.35), Inches(3.05), Inches(5.7), rcol)
    tb(slide, ricon, rx2, Inches(1.55), Inches(3.05), Inches(0.7),
       size=28, align=PP_ALIGN.CENTER)
    tb(slide, rname, rx2, Inches(2.32), Inches(3.05), Inches(0.48),
       size=15, bold=True, color=rcol, align=PP_ALIGN.CENTER)
    rect(slide, rx2 + Inches(0.5), Inches(2.85),
         Inches(2.05), Inches(0.05), fill=rcol)
    iy2 = Inches(3.0)
    for item in ritems:
        rect(slide, rx2 + Inches(0.2), iy2, Inches(0.1), Inches(0.1), fill=rcol)
        tb(slide, item, rx2 + Inches(0.4), iy2 - Inches(0.04),
           Inches(2.5), Inches(0.55), size=13, color=TXT_D)
        iy2 += Inches(0.62)
    rx2 += Inches(3.25)

# 로드맵 타임라인
rect(slide, Inches(0.35), Inches(7.1), W - Inches(0.7), Inches(0.6), fill=INDIGO)
phases = ["Phase 1  ✅", "Phase 2  🔄  현재", "Phase 3  📋", "Phase 4  🔮"]
ph_x = Inches(0.6)
for ph in phases:
    tb(slide, ph, ph_x, Inches(7.15), Inches(2.8), Inches(0.48),
       size=13, color=WHITE if "현재" not in ph else AMBER, bold=("현재" in ph),
       align=PP_ALIGN.CENTER)
    ph_x += Inches(3.1)

# ════════════════════════════════════════════════════════════════
#  S15 – 마무리
# ════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(blank_layout)

# 배경
rect(slide, 0, 0, W * 0.58, H, fill=INDIGO_D)
rect(slide, W * 0.58, 0, W * 0.42, H, fill=BG)

# 장식 원
for cx6, cy6, cr2, col6 in [
    (W * 0.82, Inches(1.5), Inches(3.5), INDIGO_L),
    (W * 0.72, Inches(5.5), Inches(2.0), TEAL_L),
]:
    rect(slide, cx6 - cr2/2, cy6 - cr2/2, cr2, cr2, fill=col6)

# 강조 선
rect(slide, 0, 0, W * 0.58, Inches(0.08), fill=TEAL)
rect(slide, Inches(0.6), Inches(0.12), Inches(0.08), H - Inches(0.25), fill=TEAL)

tb(slide, "마무리",
   Inches(0.88), Inches(0.75), Inches(7), Inches(0.65),
   size=22, color=TEAL, bold=True)

tb(slide, "정보공개의\n다음 단계는\n정보 활용",
   Inches(0.88), Inches(1.45), Inches(7.5), Inches(2.0),
   size=40, bold=True, color=WHITE)

rect(slide, Inches(0.88), Inches(3.55),
     Inches(4.5), Inches(0.07), fill=AMBER)

msgs = [
    "OpenAlio MCP는 공공기관 정보공개 체계를",
    "AI 시대에 맞게 확장하기 위한 실험입니다.",
    "",
    "국민과 행정이 공공기관 정보를 더 쉽고",
    "효과적으로 활용할 수 있도록 지원합니다.",
]
my2 = Inches(3.78)
for msg in msgs:
    tb(slide, msg, Inches(0.88), my2, Inches(7.5), Inches(0.38),
       size=16, color=INDIGO_L if msg else INDIGO_L)
    my2 += Inches(0.38)

# 핵심 키워드
kws2 = [
    ("🔗", "개방성", "오픈소스\n누구나 기여", TEAL, TEAL_L),
    ("⚡", "연결성", "AI-데이터\n표준 연결", INDIGO, INDIGO_L),
    ("💡", "활용성", "질문 한 번\n즉시 분석", AMBER_D, RGBColor(0xFF,0xF3,0xCD)),
]
kx2 = Inches(0.88)
for kicon, kword, kdesc, kcol, kcol_l in kws2:
    rect(slide, kx2, Inches(5.72), Inches(1.85), Inches(1.38),
         fill=kcol, line_color=kcol, line_w=Pt(0))
    tb(slide, kicon, kx2, Inches(5.8), Inches(1.85), Inches(0.55),
       size=22, align=PP_ALIGN.CENTER, color=WHITE)
    tb(slide, kword, kx2, Inches(6.3), Inches(1.85), Inches(0.42),
       size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    tb(slide, kdesc, kx2, Inches(6.68), Inches(1.85), Inches(0.4),
       size=11, color=WHITE, align=PP_ALIGN.CENTER)
    kx2 += Inches(2.0)

tb(slide, "감사합니다",
   Inches(0.88), Inches(7.05), Inches(5), Inches(0.52),
   size=30, bold=True, color=AMBER)

# ── 저장 ──────────────────────────────────────────────────────────
out = "/home/user/open-ALIO-mcp/OpenAlio_MCP_발표자료.pptx"
prs.save(out)
print(f"저장 완료: {out}")
