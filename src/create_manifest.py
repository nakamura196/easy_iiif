import pandas as pd
import json
import argparse
from pathlib import Path
import sys
import os
from dotenv import load_dotenv
import requests
from tqdm import tqdm

def load_data(base_path, field_id):
    """CSVファイルからデータを読み込む"""
    item_df = pd.read_csv(Path(base_path) / f"{field_id}" / "item.csv")
    media_df = pd.read_csv(Path(base_path) / f"{field_id}" / "media.csv")
    return item_df, media_df

def get_image_info(info_json_url):
    """IIIF info.jsonからwidth、heightを取得"""
    try:
        response = requests.get(info_json_url)
        response.raise_for_status()
        info = response.json()
        return info.get('width', 1000), info.get('height', 1000)
    except Exception as e:
        print(f"警告: info.jsonの取得に失敗しました ({info_json_url}): {str(e)}")
        return 1000, 1000  # デフォルト値を返す

def create_manifest(field_id, item_df, media_df, version="3"):
    """指定されたIDのマニフェストを作成"""
    # .envから設定を読み込む
    load_dotenv()
    host = os.getenv('HOST', 'https://example.org')
    
    # アイテム情報を取得
    item_data = item_df[item_df['field_id'] == field_id]
    if item_data.empty:
        raise ValueError(f"指定されたID '{field_id}' のアイテムが見つかりませんでした。")
    
    item = item_data.iloc[0]
    
    # メディア情報を取得
    media_items = media_df[media_df['field_id'] == field_id]
    if media_items.empty:
        raise ValueError(f"指定されたID '{field_id}' のメディアデータが見つかりませんでした。")
    
    if version == "3":
        context = "http://iiif.io/api/presentation/3/context.json"
        service_type = "ImageService3"
    else:  # v2
        context = "http://iiif.io/api/presentation/2/context.json"
        service_type = "ImageService2"
    
    manifest = {
        "@context": context,
        "id": f"{host}/iiif/{version}/{field_id}/manifest.json",
        "type": "Manifest",
        "label": {"ja": [item['title']]} if version == "3" else {"@value": item['title'], "@language": "ja"},
        "items" if version == "3" else "sequences": []
    }
    
    if version == "2":
        manifest["sequences"] = [{
            "@type": "sc:Sequence",
            "canvases": []
        }]
    
    # キャンバスを追加
    for index, media in tqdm(media_items.iterrows(), total=len(media_items), desc=f"{version}マニフェスト作成中"):
        # メディアタイプがIIIFの場合、info.jsonからサイズを取得
        width, height = (1000, 1000)  # デフォルト値
        if media['field_type'] == 'iiif':
            width, height = get_image_info(media['field_url'])
        
        canvas = {
            "id": f"{host}/iiif/{version}/{field_id}/canvas/p{index + 1}",
            "type": "Canvas",
            "height": height,
            "width": width,
        }
        
        if version == "3":
            canvas["items"] = [{
                "id": f"{host}/iiif/{version}/{field_id}/page/p{index + 1}/1",
                "type": "AnnotationPage",
                "items": [{
                    "id": f"{host}/iiif/{version}/{field_id}/annotation/p{index + 1}-image",
                    "type": "Annotation",
                    "motivation": "painting",
                    "body": {
                        "id": media['field_url'],
                        "type": "Image",
                        "format": "image/jpeg",
                        "service": [{
                            "id": media['field_url'].split('/info.json')[0],
                            "type": service_type,
                            "profile": "level2"
                        }]
                    },
                    "target": f"{host}/iiif/{version}/{field_id}/canvas/p{index + 1}"
                }]
            }]
        else:  # v2
            canvas["images"] = [{
                "@type": "oa:Annotation",
                "motivation": "sc:painting",
                "resource": {
                    "@id": media['field_url'],
                    "@type": "dctypes:Image",
                    "format": "image/jpeg",
                    "service": {
                        "@context": "http://iiif.io/api/image/2/context.json",
                        "@id": media['field_url'].split('/info.json')[0],
                        "profile": "http://iiif.io/api/image/2/level2.json"
                    }
                },
                "on": f"{host}/iiif/{version}/{field_id}/canvas/p{index + 1}"
            }]
        
        if version == "3":
            manifest["items"].append(canvas)
        else:
            manifest["sequences"][0]["canvases"].append(canvas)
    
    return manifest

def main():
    parser = argparse.ArgumentParser(description='IIIFマニフェストを作成')
    parser.add_argument('field_id', help='作成するマニフェストのID')
    parser.add_argument('--data-dir', default='./data', help='データディレクトリのパス')
    parser.add_argument('--output-dir', default='../docs/iiif', help='出力ディレクトリのパス')
    
    args = parser.parse_args()
    
    try:
        # データの読み込み
        item_df, media_df = load_data(args.data_dir, args.field_id)
        
        # v2とv3のマニフェストを作成
        for version in ["2", "3"]:
            manifest = create_manifest(args.field_id, item_df, media_df, version)
            
            # 出力ディレクトリの作成
            output_dir = Path(args.output_dir) / version / args.field_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # マニフェストの保存
            output_path = output_dir / "manifest.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            
            print(f"{version}マニフェストを作成しました: {output_path}")
    
    except ValueError as e:
        print(f"エラー: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
