from pathlib import Path
import numpy as np
import streamlit as st
from src.auto_guide import GuideService, load_config

st.set_page_config(page_title='SCAT 自動追尾', layout='wide')
st.title('SCAT 自動追尾')


@st.cache_resource
def service():
    # One shared worker prevents multiple browser sessions opening the same camera.
    return GuideService(load_config(Path(__file__).with_name('.config')))


try:
    guide = service()
except Exception as exc:
    st.error(str(exc))
    st.stop()
st.caption('シミュレーション（機器への送信なし）' if guide.c['simulation'] else '実機モード')
st.caption('設定変更後はアプリを再起動してください。操作状態は全ブラウザで共有されます。')


@st.fragment(run_every=.5)
def panel():
    s = guide.snapshot()
    st.subheader(s['state'])
    a, b, c, d = st.columns(4)
    if a.button('準備開始', disabled=s['state'] not in ('未接続', 'エラー')):
        guide.prepare()
    if b.button('追尾開始', disabled=s['state'] not in ('準備完了', '追尾終了')):
        guide.start()
    if c.button('追尾終了', disabled=s['state'] not in ('追尾中', '追尾開始中')):
        guide.stop()
    if d.button('カメラ接続オフ', disabled=s['state'] == '未接続'):
        guide.disconnect()
    if s['error']:
        st.error(s['error'])
    st.write({k: s[k] for k in ('frame', 'slit', 'target', 'offset', 'correction', 'matrix') if k in s})
    if s['image'] is not None:
        image = s['image']
        lo, hi = np.percentile(image, [1, 99.8])
        rgb = np.repeat(np.clip((image-lo)/max(hi-lo, 1), 0, 1)[..., None], 3, axis=2)
        for key, color in [('slit', [1., 0., 0.]), ('target', [0., 1., 0.])]:
            if key in s:
                x, y = np.rint(s[key]).astype(int)
                if 0 <= y < rgb.shape[0] and 0 <= x < rgb.shape[1]:
                    rgb[max(y-7, 0):y+8, x] = color
                    rgb[y, max(x-7, 0):x+8] = color
        st.image(rgb, caption='赤: スリット中心 / 緑: 追尾対象')


panel()
