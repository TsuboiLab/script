from pathlib import Path
import numpy as np
import streamlit as st
from src.auto_guide import GuideService, load_config
from src.base__nishimura_controler import NishimuraController

st.set_page_config(page_title='SCAT 自動追尾', layout='wide')

# GuideServiceはカメラを所有する唯一のワーカーを作成するため、
# Streamlitの再実行でカメラ接続が複数生成されないようresource cacheを使う。
@st.cache_resource
def service():
    return GuideService(load_config(Path(__file__).with_name('.config')))

try:
    guide = service()
except Exception as exc:
    st.error(str(exc)); st.stop()

@st.cache_resource
def nishimura():
    # Master2018のプロセス読み取りとGUI操作を共有する制御オブジェクト。
    # 実機アクセスにはlaunch_admin.py経由の管理者起動を使用する。
    return NishimuraController()

st.markdown("""
<style>
.block-container {padding-top: .25rem; padding-bottom: .25rem;}
.st-key-image_area {height: 51vh; min-height: 240px; overflow: visible;}
.st-key-image_area [data-testid="stImage"] img {max-height: 44vh; object-fit: contain;}
[data-testid="stVerticalBlock"] {gap: .4rem;}
/* 狭いブラウザでも画像欄と操作欄を縦積みにせず、操作タブを右側に保持する。 */
[data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; align-items: flex-start;}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width: 0 !important;}
@media (max-width: 900px) {
    .st-key-image_area {height: 51vh; min-height: 240px;}
    .st-key-image_area [data-testid="stImage"] img {max-height: 44vh;}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {flex: 1.35 1 0% !important;}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {flex: 1 1 0% !important;}
}
</style>
""", unsafe_allow_html=True)
# 上端の描画領域を確保するための空タイトル。画面上は文字を表示しない。
st.title('\u00a0')

def render_image(s):
    """最新画像を表示し、検出点と現在の補正値を重ねる。"""
    image = s.get('image')
    if image is None:
        st.info('撮像画像はここに表示されます'); return
    manual = st.session_state.get('manual_contrast', False)
    if manual:
        lo = st.session_state.get('contrast_min', float(np.nanmin(image)))
        hi = st.session_state.get('contrast_max', float(np.nanmax(image)))
    else:
        lo, hi = np.percentile(image, [1, 99.8])
    if hi <= lo:
        hi = lo + 1
    rgb = np.repeat(np.clip((image-lo)/max(hi-lo, 1), 0, 1)[..., None], 3, axis=2)
    for key, color in [('slit', [1., 1., 0.]), ('target', [1., 0., 0.])]:
        if key in s:
            x, y = np.rint(s[key]).astype(int)
            if 0 <= y < rgb.shape[0] and 0 <= x < rgb.shape[1]:
                yy, xx = np.ogrid[max(y-5,0):min(y+6,rgb.shape[0]), max(x-5,0):min(x+6,rgb.shape[1])]
                patch = rgb[max(y-5,0):min(y+6,rgb.shape[0]), max(x-5,0):min(x+6,rgb.shape[1])]
                patch[(xx-x)**2+(yy-y)**2 <= 25] = color
    for point in s.get('calibration_points', []):
        x, y = np.rint(point).astype(int)
        if 0 <= y < rgb.shape[0] and 0 <= x < rgb.shape[1]:
            yy, xx = np.ogrid[max(y-5,0):min(y+6,rgb.shape[0]), max(x-5,0):min(x+6,rgb.shape[1])]
            patch = rgb[max(y-5,0):min(y+6,rgb.shape[0]), max(x-5,0):min(x+6,rgb.shape[1])]
            patch[(xx-x)**2+(yy-y)**2 <= 25] = [0., 1., 0.]
    st.image(rgb, caption='黄: 固定スリット位置　赤: 選択天体　緑: 校正時の4位置', width='stretch')
    o=s.get('offset',[0,0]); q=s.get('correction',[0,0])
    needed = s.get('correction_needed', False)
    distance = s.get('correction_distance_px', float(np.linalg.norm(o)))
    st.caption(f'pixelズレ X={o[0]:.3f}, Y={o[1]:.3f} px　距離={distance:.3f} px　'
               f'補正要否: {"必要" if needed else "不要（各軸10px以内）"}')
    st.caption(f'RA/Dec補正値 [{q[0]:.4g}, {q[1]:.4g}] 秒角')
    if s.get('response_samples') is not None:
        status = '有効' if s.get('matrix_ready') else '学習中'
        st.caption(f'混合行列: {status}（有効サンプル {s["response_samples"]}/5）')
    if s.get('sent_correction') is not None:
        st.caption(f"送信: guide 相対補正 RA={s['sent_correction'][0]:.4g}, Dec={s['sent_correction'][1]:.4g} 秒角")

@st.fragment(run_every=.5)
def panel():
    """0.5秒ごとに、撮像・カメラ状態・MoT状態を更新する画面本体。"""
    s = guide.snapshot()
    image_col, control_col = st.columns([1.65, 1], gap='large')
    with image_col:
        st.subheader('撮像画像')
        manual = st.session_state.get('manual_contrast', False)
        image = s.get('image')
        default_min = float(np.nanmin(image)) if image is not None else 0.0
        default_max = float(np.nanmax(image)) if image is not None else 1.0
        if 'contrast_min' not in st.session_state:
            st.session_state.contrast_min = default_min
        if 'contrast_max' not in st.session_state:
            st.session_state.contrast_max = default_max
        with st.container(key='image_area'):
            render_image(s)
        histogram_col, gain_col = st.columns([1.25, 1])
        with histogram_col:
            st.caption('画像輝度ヒストグラム')
            if s.get('image') is not None:
                values = np.asarray(s['image'], dtype=float).ravel()
                values = values[np.isfinite(values)]
                hist, edges = np.histogram(values, bins=48)
                chart_data = [{'lower': float(lo), 'upper': float(hi), 'ピクセル数 個': int(count)}
                              for count, lo, hi in zip(hist, edges[:-1], edges[1:])]
                st.vega_lite_chart(spec={'data': {'values': chart_data}, 'mark': {'type': 'bar', 'binSpacing': 0, 'color': '#4c9aff'}, 'encoding': {
                    'x': {'field': 'lower', 'type': 'quantitative', 'bin': 'binned', 'title': 'カウント数 cnt'},
                    'x2': {'field': 'upper'},
                    'y': {'field': 'ピクセル数 個', 'type': 'quantitative', 'title': 'ピクセル数 個', 'axis': {'labelFontSize': 9, 'titleFontSize': 10}}},
                    'height': 180, 'config': {'axis': {'labelFontSize': 9, 'titleFontSize': 10}}}, key=f"histogram-{s.get('frame', 0)}")
            else:
                # 最初の撮像前にも、グラフの表示場所を明示する。
                with st.container(height=200, border=True):
                    st.empty()
            contrast_cols = st.columns(3)
            contrast_cols[0].toggle('コントラスト手動設定', value=st.session_state.get('manual_contrast', False), key='manual_contrast')
            st.session_state.contrast_min = contrast_cols[1].number_input('下限', value=float(st.session_state.contrast_min), key='contrast_min_input')
            st.session_state.contrast_max = contrast_cols[2].number_input('上限', value=float(st.session_state.contrast_max), key='contrast_max_input')
        with gain_col:
            st.caption('補正gain')
            auto_gain = bool(guide.c.get('auto_gain_enabled', True))
            # 自動モードでは、ワーカーが更新した現在値を表示し、入力を無効化する。
            # 手動モードでは、UI入力値を次回の追尾開始時に使用する。
            if auto_gain:
                if s.get('gain_ra') is not None:
                    st.session_state['gain_ra'] = float(s['gain_ra'])
                if s.get('gain_dec') is not None:
                    st.session_state['gain_dec'] = float(s['gain_dec'])
            gain_cols = st.columns(2)
            gain_ra = gain_cols[0].number_input('RA方向 gain', value=float(guide.c.get('gain_ra', guide.c.get('gain', 1.0))), step=0.01, disabled=auto_gain, key='gain_ra', help='正負を含む任意の有限値を指定できます')
            gain_dec = gain_cols[1].number_input('Dec方向 gain', value=float(guide.c.get('gain_dec', guide.c.get('gain', 1.0))), step=0.01, disabled=auto_gain, key='gain_dec', help='正負を含む任意の有限値を指定できます')
            if not auto_gain:
                guide.c['gain_ra'], guide.c['gain_dec'] = gain_ra, gain_dec
            guide.c['auto_gain_enabled'] = st.radio(
                'gain補正', ['自動', '手動'],
                index=0 if bool(guide.c.get('auto_gain_enabled', True)) else 1,
                horizontal=True,
                format_func=lambda mode: mode,
                help='自動: 補正後のズレに応じてgain値を調整。手動: 入力したgain値を固定') == '自動'

    with control_col:
        tracking_tab, mot_main_tab = st.tabs(['基本操作', '開発用オプション'])
        with tracking_tab:
            with st.container(height=246, border=False):
                a, b = st.columns(2)
                idle = s['state'] in ('準備完了', '追尾終了')
                a.button('カメラ電源ON', disabled=s['state'] not in ('未接続', 'エラー'), on_click=guide.connect, width='stretch')
                b.button('カメラ電源OFF', disabled=not s.get('connected'), on_click=guide.disconnect, width='stretch')
                a, b = st.columns(2)
                a.button('冷却ON', disabled=not idle, on_click=guide.cool, width='stretch')
                b.button('冷却OFF', disabled=not s.get('connected'), on_click=guide.cool_off, width='stretch')
                a, b = st.columns(2)
                a.button('ループ撮像ON', disabled=not idle, on_click=guide.start_capture, width='stretch')
                b.button('ループ撮像OFF', disabled=s['state'] not in ('連続撮像中', '追尾中', '追尾開始中', '校正中'), on_click=guide.stop, width='stretch')
                a, b = st.columns(2)
                a.button('スリット前回位置利用', on_click=guide.use_initial_slit, disabled=s['state'] in ('追尾中', '追尾開始中'), width='stretch')
                b.button('スリット位置検知', on_click=guide.detect_slit_position, width='stretch', disabled=s['state'] in ('追尾中', '追尾開始中'))
                st.button('天体検知', on_click=guide.detect_target_position, width='stretch')
                a, b = st.columns(2)
                a.button('追尾用calibration', disabled=s['state'] != '連続撮像中', on_click=guide.calibrate_tracking, width='stretch')
                b.caption(f"最終校正日時: {s.get('calibration_time', '未校正')}")
                a, b = st.columns(2)
                a.button('自動追尾ON', disabled=s['state'] != '連続撮像中' or 'slit' not in s or not s.get('calibration_ready'), on_click=guide.start, width='stretch')
                b.button('自動追尾OFF', disabled=s['state'] not in ('追尾中', '追尾開始中'), on_click=guide.stop_tracking, width='stretch')
            if 'slit' in s:
                st.caption(f"スリット中心 X={s['slit'][0]:.2f}, Y={s['slit'][1]:.2f} pix ／ {s.get('slit_origin', '検出値')}")
            if s.get('sources'):
                st.dataframe([{'順位': i+1, 'X [pix]': round(p['x'], 2), 'Y [pix]': round(p['y'], 2),
                               '明るさ（背景差引積算）': round(p['flux'], 1),
                               '選択': i+1 == guide.c['target_brightness_rank']}
                              for i, p in enumerate(s['sources'][:5])], hide_index=True)
            st.subheader('カメラステータス')
            st.write(f"**コネクト状態**　{'ON' if s.get('connected') else 'OFF'}")
            cooling_status = '変更中' if s.get('state') == '冷却中' else ('ON' if s.get('cooling') else 'OFF')
            st.write(f"**冷却状態**　{cooling_status}")
            temp_cols = st.columns(2)
            t=s.get('temperature')
            temp_cols[0].metric('カメラ温度', f'{float(t):.1f} °C' if t is not None else '--.- °C')
            guide.c['temperature_c'] = temp_cols[1].number_input(
                '目標温度 °C', value=float(guide.c.get('temperature_c', 0.0)),
                step=0.1, format='%.1f', key='target_temperature_c')
            st.write(f"**撮像状態**　{s.get('imaging_state','待機中')}")
            st.write(f"**操作状態**　{s['state']}　（Frame {s['frame']}）")
            if s.get('save_error'):
                st.warning(f"画像保存は保留中です（撮像は継続）: {s['save_error']}")
            exposure = st.number_input(
                '露光時間 (秒)', min_value=0.001, value=float(guide.c.get('exposure_sec', 0.5)),
                step=0.1, format='%.3f', key='exposure_sec_input',
                on_change=lambda: guide.set_exposure(
                    float(st.session_state.exposure_sec_input)))
            # 再描画では再送せず、ユーザーが変更を確定した時だけ予約する。
            st.caption(f'要求値: {exposure:.3f} 秒 ／ 適用値: {guide.c["exposure_sec"]:.3f} 秒')
            if s.get('exposure_error'):
                st.warning(s['exposure_error'])
            if s.get('error'): st.error(s['error'])
        with mot_main_tab:
            mot = nishimura()
            st.caption('MoT操作は対象タブを自動照合します。制御タブの電源ON後に他操作が有効になります。')
            if st.button('MoT起動', width='stretch'):
                try: st.json(mot.start_master())
                except Exception as exc: st.error(str(exc))
            telescope_tab, dome_tab, control_tab, symbol_tab = st.tabs(['望遠鏡', 'ドーム', '制御', '記号'])
            def mot_button(label, action):
                if st.button(label, width='stretch', key=f'mot-{action}-{label}'):
                    try: st.json(mot.send(action) if action == 'ending' else mot.click(action))
                    except Exception as exc: st.error(str(exc))
            with telescope_tab:
                mot_button('恒星追尾モードon', 'sidereal:on')
                mot_button('恒星追尾モードoff', 'sidereal:off')
            with dome_tab:
                mot_button('ドームスリットopen', 'slit:open')
                mot_button('ドームスリットclose', 'slit:close')
                mot_button('ドームスリット停止', 'slit:stop')
                mot_button('ドーム右回転ON', 'dome:right')
                mot_button('ドーム左回転ON', 'dome:left')
                mot_button('ドーム回転OFF', 'dome:stop')
            with control_tab:
                mot_button('コントローラ電源ON', 'power:on')
                mot_button('コントローラ電源OFF', 'power:off')
            with symbol_tab:
                mot_button('観測終了処理', 'ending')
        with tracking_tab:
            try:
                pos = nishimura().read_position()
                ra, dec = pos['ra_j2000_hours'], pos['dec_j2000_deg']
                correction = s.get('correction', [0.0, 0.0])
                corrected_ra = (ra + correction[0] / 54000.0) % 24.0
                corrected_dec = dec + correction[1] / 3600.0
                st.caption('MoT現在位置（約0.5秒更新）')
                st.write(f"**鏡筒 RA (J2000)**　{ra:.8f} h　→ 補正後 {corrected_ra:.8f} h")
                st.write(f"**鏡筒 Dec (J2000)**　{dec:.8f} °　→ 補正後 {corrected_dec:.8f} °")
                st.write(f"**鏡筒方向 方位**　{pos['azimuth_software_deg']:.8f} °")
                st.write(f"**鏡筒方向 高度**　{pos['altitude_software_deg']:.8f} °")
                st.write(f"**ドーム方向 方位**　{pos['raw']['DomRotDir']:.8f} °")
                st.write(f"**適用補正値**　RA {correction[0]:.4g} 秒角 / Dec {correction[1]:.4g} 秒角")
            except Exception as exc:
                st.warning(f'西村MoT現在位置を取得できません: {exc}')

panel()
