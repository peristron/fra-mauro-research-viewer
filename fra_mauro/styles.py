APP_CSS = """
<style>
    :root {
        --ink: #202421;
        --muted: #69716b;
        --paper: #f5f2ea;
        --accent: #9f3f32;
        --line: #d7d0c2;
        --water: #356f87;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(245, 242, 234, .92); }
    [data-testid="stSidebar"] { background: #ece7dc; border-right: 1px solid var(--line); }
    h1, h2, h3 { letter-spacing: 0 !important; color: var(--ink); }
    h1 { font-family: Georgia, serif; font-size: 2rem !important; }
    .fm-kicker { color: var(--accent); font-size: .75rem; font-weight: 700; text-transform: uppercase; }
    .fm-subtle { color: var(--muted); font-size: .88rem; }
    .fm-status { border-left: 3px solid var(--water); padding: .55rem .8rem; background: #edf2f1; }
    .fm-warning { border-left: 3px solid var(--accent); padding: .55rem .8rem; background: #f4e9e4; }
    .fm-metric { font-size: 1.35rem; font-weight: 650; }
    .fm-label { color: var(--muted); font-size: .75rem; text-transform: uppercase; }
    div[data-testid="stDataFrame"] { border: 1px solid var(--line); }
    .stButton > button, .stDownloadButton > button { border-radius: 4px; }
    .stTabs [data-baseweb="tab-list"] { gap: .4rem; border-bottom: 1px solid var(--line); }
    .stTabs [data-baseweb="tab"] { border-radius: 0; }
</style>
"""
