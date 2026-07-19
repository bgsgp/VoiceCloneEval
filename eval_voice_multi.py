#!/usr/bin/env python3
"""
克隆音频评估（相似度 + DNSMOS + 雷达图）
版本 2.1 - 雷达文字带描边双主题清晰可见、表格每项增加评级后缀、持久临时目录修复图片失效、版本号固定灰色
"""

import gradio as gr
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patheffects import withStroke
from matplotlib.font_manager import FontProperties
from resemblyzer import VoiceEncoder, preprocess_wav
from speechmos import dnsmos
import os
import tempfile
import uuid

VERSION = "2.1"

# ---------- 强制使用微软雅黑 ----------
FONT_PATH = r'C:\Windows\Fonts\msyh.ttc'
if not os.path.exists(FONT_PATH):
    FONT_PATH = r'C:\Windows\Fonts\msyhbd.ttc'

if os.path.exists(FONT_PATH):
    chinese_font = FontProperties(fname=FONT_PATH, size=12)
    print(f"✅ 已使用微软雅黑字体: {FONT_PATH}")
else:
    print("⚠️ 未找到微软雅黑，将使用系统默认字体（可能显示方框）")
    chinese_font = None

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.size'] = 14

_encoder = None

def get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = VoiceEncoder()
    return _encoder

# ---------------------- 评级工具函数 ----------------------
def get_sim_rank(val):
    if np.isnan(val):
        return "ERR"
    if val >= 0.90:
        return "A"
    elif val >= 0.80:
        return "B"
    elif val >= 0.70:
        return "C"
    elif val >= 0.60:
        return "D"
    else:
        return "E"

def get_mos_rank(val):
    if np.isnan(val):
        return "ERR"
    if val >= 4.0:
        return "A"
    elif val >= 3.5:
        return "B"
    elif val >= 3.0:
        return "C"
    elif val >= 2.5:
        return "D"
    else:
        return "E"

# ---------- 单个音频评估 ----------
def evaluate_single(ref_wav, test_audio_path, encoder):
    try:
        test_wav = preprocess_wav(Path(test_audio_path))
        emb_ref = encoder.embed_utterance(ref_wav)
        emb_test = encoder.embed_utterance(test_wav)
        similarity = float(np.dot(emb_ref, emb_test))
    except Exception:
        similarity = np.nan

    try:
        result = dnsmos.run(str(test_audio_path), sr=16000)
        ovrl = float(result.get("ovrl_mos", np.nan))
        sig = float(result.get("sig_mos", np.nan))
        bak = float(result.get("bak_mos", np.nan))
        p808 = float(result.get("p808_mos", np.nan))
    except Exception:
        ovrl = sig = bak = p808 = np.nan

    return {
        "Similarity": similarity,
        "OVRL": ovrl,
        "SIG": sig,
        "BAK": bak,
        "P808": p808
    }

# ---------- 绘制雷达图：文字白色描边，深浅主题都清晰 ----------
def plot_radar_temp(scores, filename, temp_dir):
    labels = ['相似度', 'OVRL', 'SIG', 'BAK', 'P808']
    values = [
        scores['Similarity'] * 5,
        scores['OVRL'],
        scores['SIG'],
        scores['BAK'],
        scores['P808']
    ]
    # 文字样式：黑色主体+白色粗描边，深色/浅色背景都能看清
    text_effect = [withStroke(linewidth=2, foreground="white")]
    text_color = "#111111"
    grid_color = "#666666"
    red_color = "#c82423"
    red_effect = [withStroke(linewidth=1.8, foreground="white")]

    fig, ax = plt.subplots(figsize=(5, 5))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    if any(np.isnan(v) for v in values):
        txt = ax.text(0.5, 0.5, "数据无效", ha='center', va='center', fontsize=16,
                color=text_color, path_effects=text_effect, fontproperties=chinese_font if chinese_font else None)
        ax.set_title(filename, fontsize=14, color=text_color, path_effects=text_effect, fontproperties=chinese_font if chinese_font else None)
    else:
        angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]

        plt.close(fig)
        fig, ax = plt.subplots(figsize=(5, 5), subplot_kw=dict(polar=True))
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")
        ax.plot(angles, values, 'o-', linewidth=2.5, color='#1f77b4')
        ax.fill(angles, values, alpha=0.25, color='#1f77b4')
        ax.set_rlim(0, 5)
        ax.set_rticks([1, 2, 3, 4, 5])
        ax.set_yticklabels(['1', '2', '3', '4', '5'], color=grid_color, size=10, path_effects=text_effect)
        ax.set_xticks(angles[:-1])

        if chinese_font:
            ax.set_xticklabels(labels, fontsize=16, fontweight='bold', va='center',
                               color=text_color, path_effects=text_effect, fontproperties=chinese_font)
            ax.set_title(filename, fontsize=14, pad=25, color=text_color, path_effects=text_effect, fontproperties=chinese_font)
            ax.text(0, 0, f"相似度={scores['Similarity']:.2f}", ha='center', va='center',
                    fontsize=13, color=red_color, path_effects=red_effect, fontproperties=chinese_font)
        else:
            ax.set_xticklabels(labels, fontsize=16, fontweight='bold', va='center', color=text_color, path_effects=text_effect)
            ax.set_title(filename, fontsize=14, pad=25, color=text_color, path_effects=text_effect)
            ax.text(0, 0, f"相似度={scores['Similarity']:.2f}", ha='center', va='center',
                    fontsize=13, color=red_color, path_effects=red_effect)

        ax.grid(True, linestyle='--', alpha=0.5, color=grid_color)
        ax.tick_params(pad=10)

    temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}.png")
    fig.savefig(temp_path, bbox_inches='tight', transparent=True, pad_inches=0.1)
    plt.close(fig)
    return temp_path

# ---------- 主评估：表格每项拼接评级 x.xx-A ----------
def evaluate_batch(ref_audio_path, test_file_list):
    if not ref_audio_path:
        return pd.DataFrame(columns=["文件名", "相似度", "OVRL", "SIG", "BAK", "P808"]), []
    if not test_file_list:
        return pd.DataFrame(columns=["文件名", "相似度", "OVRL", "SIG", "BAK", "P808"]), []

    if isinstance(test_file_list, list):
        test_audio_paths = []
        for item in test_file_list:
            if isinstance(item, dict) and 'name' in item:
                test_audio_paths.append(item['name'])
            elif isinstance(item, str):
                test_audio_paths.append(item)
            else:
                test_audio_paths.append(str(item))
    else:
        test_audio_paths = [str(test_file_list)]

    try:
        ref_wav = preprocess_wav(Path(ref_audio_path))
    except Exception as e:
        return pd.DataFrame(columns=["文件名", "相似度", "OVRL", "SIG", "BAK", "P808"]), []

    encoder = get_encoder()
    results = {}
    for audio_path in test_audio_paths:
        name = Path(audio_path).name
        results[name] = evaluate_single(ref_wav, audio_path, encoder)

    df_data = []
    for name, scores in results.items():
        # 相似度带评级
        sim_val = scores['Similarity']
        sim_rank = get_sim_rank(sim_val)
        sim_str = f"{sim_val:.4f}-{sim_rank}" if not np.isnan(sim_val) else "Error-ERR"

        # MOS各项带评级
        ovrl_val = scores['OVRL']
        ovrl_rank = get_mos_rank(ovrl_val)
        ovrl_str = f"{ovrl_val:.3f}-{ovrl_rank}" if not np.isnan(ovrl_val) else "Error-ERR"

        sig_val = scores['SIG']
        sig_rank = get_mos_rank(sig_val)
        sig_str = f"{sig_val:.3f}-{sig_rank}" if not np.isnan(sig_val) else "Error-ERR"

        bak_val = scores['BAK']
        bak_rank = get_mos_rank(bak_val)
        bak_str = f"{bak_val:.3f}-{bak_rank}" if not np.isnan(bak_val) else "Error-ERR"

        p808_val = scores['P808']
        p808_rank = get_mos_rank(p808_val)
        p808_str = f"{p808_val:.3f}-{p808_rank}" if not np.isnan(p808_val) else "Error-ERR"

        df_data.append({
            "文件名": name,
            "相似度": sim_str,
            "OVRL": ovrl_str,
            "SIG": sig_str,
            "BAK": bak_str,
            "P808": p808_str
        })
    df = pd.DataFrame(df_data)

    # 持久临时目录，解决图片加载失效
    global_tmp = tempfile.mkdtemp()
    image_paths = []
    for name, scores in results.items():
        img_path = plot_radar_temp(scores, name, global_tmp)
        image_paths.append(img_path)

    return df, image_paths

# ---------- 解读表格（自适应页面背景）
INTERPRETATION_TABLE = """
<div style="overflow-x:auto; margin-top:24px;">
    <!-- 表格居中标题 -->
    <h3 style="text-align:center; margin:0 0 12px 0; color:var(--text-primary); font-size:18px;">📊 参数解读</h3>
    <table style="width:100%; border-collapse:collapse; font-size:14px; text-align:left; background-color:var(--background-fill-primary) !important; color:var(--text-primary) !important;">
        <thead>
            <tr style="background-color:var(--background-fill-secondary) !important;">
                <th style="padding:10px; border:1px solid var(--border-color); width:12%;">指标</th>
                <th style="padding:10px; border:1px solid var(--border-color); width:44%;">官方表述（科学）</th>
                <th style="padding:10px; border:1px solid var(--border-color); width:44%;">人话表述（直观）</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><b>👤 相似度</b></td>
                <td>说话人嵌入向量的余弦相似度，反映声纹特征的匹配程度。</td>
                <td>克隆音色和原声主人像不像？数值越高，听感越贴合本人。</td>
            </tr>
            <tr>
                <td><b>🎧 OVRL</b></td>
                <td>DNSMOS总体质量评分，综合语音信号、背景噪声和失真程度。</td>
                <td>整体音频听感舒服吗？综合音质、杂音、失真的总分。</td>
            </tr>
            <tr>
                <td><b>🗣️ SIG</b></td>
                <td>DNSMOS语音信号评分，评估语音本身的清晰度和保真度。</td>
                <td>人声清不清晰？会不会发闷、含糊、有电子失真感？</td>
            </tr>
            <tr>
                <td><b>🌫️ BAK</b></td>
                <td>DNSMOS背景噪声评分，评估背景是否干净。</td>
                <td>音频背景干净吗？有没有电流杂音、环境底噪、呼吸杂音？</td>
            </tr>
            <tr>
                <td><b>⭐ P808</b></td>
                <td>ITU-T P.808 标准 MOS 分，由深度学习模型预测的主观意见分。</td>
                <td>以普通人听觉标准打分，分数越高越接近真人自然人声。</td>
            </tr>
        </tbody>
    </table>
    <div style="text-align:center; margin:10px 0 0 0;">
        <p style="color:var(--text-secondary);font-size:13px; margin:0;">
            📌 评级分级：A优秀 / B良好 / C及格 / D较差 / E很差
        </p>
    </div>
</div>
"""

# ---------- CSS：表格自适应页面底色
CUSTOM_CSS = """
#eval_btn {
    display: block !important;
    margin: 0 auto !important;
    width: 50% !important;
    min-width: 200px;
}
#eval_df table,
#eval_df thead tr,
#eval_df tbody tr,
#eval_df td,
#eval_df th {
    background-color: var(--background-fill-primary) !important;
    color: var(--text-primary) !important;
}
#eval_df th {
    background-color: var(--background-fill-secondary) !important;
}
#eval_df th, #eval_df td {
    border: 1px solid var(--border-color);
    padding: 6px 10px;
}
#eval_df .wrap {
    background: var(--background-fill-primary) !important;
}
#output_gallery {
    background: var(--background-fill-primary) !important;
}

#output_gallery .gallery-item {
    overflow: hidden !important;
    border-radius: 0 !important;
}

#output_gallery .gallery-item img {
    width: 100% !important;
    height: auto !important;
    max-height: none !important;
    object-fit: contain !important;
    object-position: center center !important;
    transform: none !important;
    zoom: 1 !important;
}

#outpu#output_gallery {
    background: var(--background-fill-primary) !important;
}
"""

empty_df = pd.DataFrame(columns=["文件名", "相似度", "OVRL", "SIG", "BAK", "P808"])

# ---------- Gradio 界面 ----------
with gr.Blocks(title=f"克隆音频综合评估 v{VERSION}") as demo:
    # 版本号固定灰色 #888
    gr.HTML(f"""
    <div style="text-align: center; font-size: 2em; font-weight: bold; margin-bottom: 10px; color:var(--text-primary);">
        🎤 克隆音频综合评估 <span style="font-size: 0.6em; color: #888;">(v{VERSION})</span>
    </div>
    """)
    gr.HTML("""
    <div style="text-align: center; margin-bottom: 20px; color:var(--text-secondary);">
        上传参考音频，然后按住 <kbd style="background:var(--background-fill-secondary); padding:2px 6px; border-radius:3px;">Ctrl</kbd> 或 <kbd style="background:var(--background-fill-secondary); padding:2px 6px; border-radius:3px;">Shift</kbd> 键选择多个待测音频进行批量评估。
    </div>
    """)

    with gr.Row(equal_height=True):
        ref_audio = gr.Audio(label="参考音频 (原始)", type="filepath", scale=1)
        test_audios = gr.File(
            label="待测音频 (可多选)",
            file_count="multiple",
            file_types=[".wav", ".mp3", ".flac", ".ogg"],
            scale=1
        )

    with gr.Row():
        eval_btn = gr.Button("🚀 开始评估", variant="primary", elem_id="eval_btn")

    with gr.Row():
        output_df = gr.Dataframe(value=empty_df, label="评估结果表格", interactive=False, scale=1, elem_id="eval_df")
        output_gallery = gr.Gallery(label="雷达图对比", columns=1, height="auto", object_fit="contain", scale=1, elem_id="output_gallery")

    gr.HTML(INTERPRETATION_TABLE)

    eval_btn.click(
        fn=evaluate_batch,
        inputs=[ref_audio, test_audios],
        outputs=[output_df, output_gallery]
    )

if __name__ == "__main__":
    demo.launch(share=False, pwa=True, css=CUSTOM_CSS)