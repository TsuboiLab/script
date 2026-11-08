"""Image coordinates are (x=column, y=row), in unbinned image pixels."""
import numpy as np
from scipy import ndimage as ndi


def image2d(image):
    a = np.asarray(image, dtype=float)
    if a.ndim != 2 or min(a.shape) < 8 or not np.isfinite(a).all():
        raise ValueError('有限値からなる2次元画像が必要です')
    return a


def slit_center(image, roi=None, *, science_image=False):
    """Return (x,y): region centroid for flats, endpoint midpoint for science."""
    return detect_slit(image, roi, science_image=science_image)['center']


def detect_illuminated_slit(image, roi=None):
    """照明ON校正画像用。照度を正規化し、縦の暗線の両端中点を返す。"""
    a = image2d(image)
    h, w = a.shape
    x0, y0, x1, y1 = roi or (0, 0, w, h)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError('スリット校正ROIが画像範囲外です')
    crop = a[y0:y1, x0:x1]
    background = ndi.gaussian_filter(crop, 12)
    dark = (background-ndi.gaussian_filter(crop, 1))/np.maximum(np.abs(background), 1.)
    noise = max(1e-6, 1.4826*np.median(np.abs(dark-np.median(dark))))
    threshold = 3*noise
    labels, count = ndi.label(ndi.binary_closing(dark > threshold, iterations=2))
    candidates = []
    for label in range(1, count+1):
        yy, xx = np.where(labels == label)
        if len(xx) < 80 or xx.min() <= 3 or yy.min() <= 3 or xx.max() >= crop.shape[1]-4 or yy.max() >= crop.shape[0]-4:
            continue
        points = np.column_stack((xx+x0, yy+y0))
        eig, vectors = np.linalg.eigh(np.cov(points.T))
        direction = vectors[:, -1]
        if eig[-1]/max(eig[0], .1) < 30 or abs(direction[1]) < .94:
            continue
        origin = points.mean(axis=0)
        along = (points-origin)@direction
        length = np.ptp(along)
        if length < max(60, .12*min(h, w)):
            continue
        endpoints = origin+np.array([along.min(), along.max()])[:, None]*direction
        candidates.append((length, dict(center=endpoints.mean(axis=0), endpoints=endpoints,
            roi=(x0,y0,x1,y1), mask=labels == label, residual=dark, threshold=threshold)))
    if not candidates:
        raise ValueError('照明ONの画像からスリットを検出できません。保存済み初期値は変更しません')
    return max(candidates, key=lambda item: item[0])[1]


def detect_slit(image, roi=None, *, science_image=False):
    """Detect a flat-image slit using relative local contrast.

    Normalizing by the local background handles illumination gradients. The
    center is the binary region centroid, preserving the original convention.
    ROI coordinates are x0,y0,x1,y1 with exclusive upper bounds.
    """
    if science_image:
        return detect_science_slit(image, roi)
    a = image2d(image)
    x0, y0, x1, y1 = roi or (0, 0, a.shape[1], a.shape[0])
    if not (0 <= x0 < x1 <= a.shape[1] and 0 <= y0 < y1 <= a.shape[0]):
        raise ValueError('slit_roi が画像範囲外です')
    crop = a[y0:y1, x0:x1]
    background = ndi.gaussian_filter(crop, 12)
    dark = (background - ndi.gaussian_filter(crop, 1)) / np.maximum(np.abs(background), 1.)
    noise = max(1e-6, 1.4826 * np.median(np.abs(dark - np.median(dark))))
    threshold = max(5 * noise, dark.max() * .2)
    labels, count = ndi.label(dark > threshold)
    candidates = []
    for label in range(1, count + 1):
        yy, xx = np.where(labels == label)
        if len(xx) < 20:
            continue
        # A complete slit must be inside the ROI, not a crop/frame edge.
        if xx.min() == 0 or yy.min() == 0 or xx.max() == crop.shape[1]-1 or yy.max() == crop.shape[0]-1:
            continue
        eig = np.linalg.eigvalsh(np.cov(xx, yy))
        if eig[-1] / max(eig[0], .1) < 9:
            continue
        candidates.append((eig[-1], label, float(xx.mean()) + x0, float(yy.mean()) + y0))
    if not candidates:
        raise ValueError('スリットを検出できません。フラット画像とROIを確認してください')
    _, label, cx, cy = max(candidates)
    return dict(center=np.array([cx, cy]), mask=labels == label,
                residual=dark, threshold=float(threshold), roi=(x0,y0,x1,y1))


def detect_science_slit(image, roi, *, smooth_sigma=3., threshold_sigma=2.5):
    """Fit a slit from aligned dark fragments in a star-containing image.

    ROI must contain the entire slit. Bright pixels are clipped for slit
    detection only; source centroiding always uses the original image.
    Center means midpoint of the detected ends, not the area centroid.
    """
    a = image2d(image)
    if roi is None or len(roi) != 4:
        raise ValueError('星像入り画像のスリット検出にはROIを指定してください')
    x0, y0, x1, y1 = roi
    if not (0 <= x0 < x1 <= a.shape[1] and 0 <= y0 < y1 <= a.shape[0]):
        raise ValueError('slit_roi が画像範囲外です')
    if smooth_sigma <= 0 or threshold_sigma <= 0:
        raise ValueError('検出パラメーターは正の値が必要です')
    crop = a[y0:y1, x0:x1]
    median = np.median(crop)
    scatter = max(1e-6, 1.4826*np.median(np.abs(crop-median)))
    clipped = np.minimum(crop, median+3*scatter)
    dark = ndi.gaussian_filter(clipped, 12)-ndi.gaussian_filter(clipped, smooth_sigma)
    noise = max(1e-6, 1.4826*np.median(np.abs(dark-np.median(dark))))
    threshold = threshold_sigma*noise
    labels, count = ndi.label(ndi.binary_closing(dark > threshold, iterations=3))
    components = []
    for label in range(1, count+1):
        yy, xx = np.where(labels == label)
        if len(xx) < 80:
            continue
        if xx.min() <= 3 or yy.min() <= 3 or xx.max() >= crop.shape[1]-4 or yy.max() >= crop.shape[0]-4:
            continue
        points = np.column_stack((xx+x0, yy+y0))
        eig, vectors = np.linalg.eigh(np.cov(points.T))
        if eig[-1]/max(eig[0], .1) >= 20:
            components.append((eig[-1], label, points, vectors[:, -1]))
    if not components:
        raise ValueError('ROI内に十分な長さのスリットを検出できません')
    _, seed_label, seed, direction = max(components, key=lambda p: p[0])
    origin = seed.mean(axis=0)
    normal = np.array([-direction[1], direction[0]])
    # First collect collinear fragments, then grow across bounded gaps.
    aligned = [c for c in components if abs(c[3]@direction) >= np.cos(np.deg2rad(12))
               and abs((c[2].mean(axis=0)-origin)@normal) < 10]
    selected = {seed_label}
    along = (seed-origin)@direction
    low, high = along.min(), along.max()
    changed = True
    while changed:
        changed = False
        for _, label, points, _ in aligned:
            along = (points-origin)@direction
            gap = max(low-along.max(), along.min()-high, 0)
            if label not in selected and gap < 100:
                selected.add(label)
                low, high = min(low, along.min()), max(high, along.max())
                changed = True
    points = np.concatenate([c[2] for c in aligned if c[1] in selected])
    origin = points.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov(points.T))
    direction = vectors[:, -1]
    if direction[1] < 0:
        direction = -direction
    along = (points-origin)@direction
    endpoints = origin+np.array([along.min(), along.max()])[:, None]*direction
    return dict(center=endpoints.mean(axis=0), mask=np.isin(labels, list(selected)),
                residual=dark, threshold=float(threshold), roi=tuple(roi),
                endpoints=endpoints, direction=direction, component_count=len(selected))


def pixel_offset(position, slit):
    """Return slit minus source in zero-based image pixels (dx, dy)."""
    position, slit = np.asarray(position, dtype=float), np.asarray(slit, dtype=float)
    if position.shape != (2,) or slit.shape != (2,) or not np.isfinite([position, slit]).all():
        raise ValueError('中心位置は有限な(x,y)座標を指定してください')
    return slit - position


def calibrate_slit(image, roi=None, *, center_hint=None):
    """最新画像のサイズに応じて全体を探索し、十分長い暗線を検出する。

    旧固定ROIを既定値に使わない。背景むらに対する局所コントラストを
    複数の平滑化幅で評価し、短いノイズ片をスリットとして採用しない。
    """
    a = image2d(image)
    h, w = a.shape
    if roi is None and center_hint is not None:
        hint = np.asarray(center_hint, dtype=float)
        if hint.shape != (2,) or not np.isfinite(hint).all() or np.any((hint <= 0) | (hint >= 1)):
            raise ValueError('スリット中心の目安は画像幅・高さに対する0〜1の比率で指定してください')
        # 目安は探索範囲にだけ使用し、返す中心は必ず画像から測定する。
        cx, cy = hint * [w, h]
        roi = [max(0, int(cx-.10*w)), max(0, int(cy-.30*h)),
               min(w, int(cx+.10*w)), min(h, int(cy+.30*h))]
    roi = roi or [int(.05*w), int(.05*h), int(.95*w), int(.95*h)]
    candidates = []
    for sigma in (1.0, 2.0, 3.0):
        try:
            candidate = detect_science_slit(a, roi, smooth_sigma=sigma)
        except ValueError:
            continue
        length = np.linalg.norm(candidate['endpoints'][1]-candidate['endpoints'][0])
        if length >= max(60, .12*min(h, w)) and abs(candidate['direction'][1]) > .94:
            candidates.append((length, candidate))
    if not candidates:
        # 弱い線は画素単位の閾値では分断されるため、長さ方向に積算する。
        # 両側より暗い線だけを採用し、照明の段差（片側のみ暗い）は抑制する。
        x0, y0, x1, y1 = roi
        crop = a[y0:y1, x0:x1]
        local = ndi.median_filter(crop, size=15)
        noise = max(1., 1.4826*np.median(np.abs(crop-local)))
        clipped = np.minimum(crop, local+3*noise)
        for angle in range(-12, 13, 2):
            rotated = ndi.rotate(clipped, angle, reshape=False, order=1, mode='nearest')
            center = ndi.gaussian_filter(rotated, (25, 1))
            left = ndi.shift(center, (0, 7), order=1, mode='nearest')
            right = ndi.shift(center, (0, -7), order=1, mode='nearest')
            response = np.minimum(left-center, right-center)
            response = ndi.rotate(response, -angle, reshape=False, order=1, mode='constant')
            sigma = max(1e-6, 1.4826*np.median(np.abs(response-np.median(response))))
            labels, count = ndi.label(response > 4*sigma)
            for label in range(1, count+1):
                yy, xx = np.where(labels == label)
                if len(xx) < 80 or xx.min() < 20 or yy.min() < 20 or xx.max() >= crop.shape[1]-20 or yy.max() >= crop.shape[0]-20:
                    continue
                points = np.column_stack((xx+x0, yy+y0))
                eig, vectors = np.linalg.eigh(np.cov(points.T))
                if eig[-1]/max(eig[0], .1) < 30:
                    continue
                direction = vectors[:, -1]
                if abs(direction[1]) < .94:
                    continue
                origin = points.mean(axis=0)
                along = (points-origin)@direction
                length = np.ptp(along)
                if length < max(60, .12*min(h, w)):
                    continue
                endpoints = origin+np.array([along.min(), along.max()])[:, None]*direction
                candidates.append((length, dict(center=endpoints.mean(axis=0), endpoints=endpoints,
                    direction=direction, roi=roi, mask=labels == label, component_count=1,
                    residual=response, threshold=4*sigma)))
    if not candidates:
        raise ValueError('スリット位置を確定できません。照明・探索範囲を確認して再検知してください')
    return max(candidates, key=lambda item: item[0])[1]


def point_sources(image, threshold_sigma=5., max_sources=5):
    a = image2d(image)
    # 行・列方向の帯と緩やかな背景を除去する。重心も同じ背景差分で測る。
    row_corrected = a - np.median(a, axis=1, keepdims=True)
    residual = row_corrected - np.median(row_corrected, axis=0, keepdims=True)
    residual -= ndi.median_filter(residual, size=21)
    noise = max(1., 1.4826 * np.median(np.abs(residual - np.median(residual))))
    smooth = ndi.gaussian_filter(residual, 1)
    peaks = (smooth == ndi.maximum_filter(smooth, size=9)) & (smooth > threshold_sigma * noise)
    yy, xx = np.where(peaks)
    sources = []
    for y, x in zip(yy, xx):
        if x < 4 or y < 4 or x >= a.shape[1] - 4 or y >= a.shape[0] - 4:
            continue
        patch = np.maximum(residual[y-4:y+5, x-4:x+5], 0)
        # Reject isolated hot pixels.
        if np.count_nonzero(patch > threshold_sigma * noise) < 3:
            continue
        py, px = np.indices(patch.shape)
        flux = float(patch.sum())
        sources.append(dict(x=float((px * patch).sum()/flux + x-4),
                            y=float((py * patch).sum()/flux + y-4), flux=flux))
    return sorted(sources, key=lambda p: p['flux'], reverse=True)[:max_sources]


def detect_frame(image, roi, *, threshold_sigma=5., max_sources=5):
    """1枚から天体とスリットを独立に検出する。未検出を架空の座標で補わない。

    スリットが写っていない場合にも天体は返す。呼び出し側はslit=Noneの
    フレームでは補正を送らず、次の画像で再検出する。
    """
    a = image2d(image)
    sources = point_sources(a, threshold_sigma, max_sources)
    try:
        slit = detect_science_slit(a, roi)
    except ValueError as exc:
        if str(exc) != 'ROI内に十分な長さのスリットを検出できません':
            raise
        return dict(slit=None, sources=sources,
                    warning='スリット未検出：補正を保留します。ROI・照明・スリットの写りを確認してください。')
    return dict(slit=slit, sources=sources, warning='')
