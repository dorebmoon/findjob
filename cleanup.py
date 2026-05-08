#!/usr/bin/env python3
"""
FindJob 临时文件清理工具

用法:
    python cleanup.py              # 交互式选择要清理的内容
    python cleanup.py --all        # 清理所有临时文件
    python cleanup.py --browser    # 仅清理浏览器配置文件 (browser_profiles/)
    python cleanup.py --db         # 仅清理数据库 (instance/)
    python cleanup.py --cache      # 仅清理 Python 缓存 (__pycache__/)
    python cleanup.py --log        # 仅清理日志文件 (*.log)
    python cleanup.py --dry-run    # 预览将要删除的文件，不实际删除
"""

import os
import sys
import shutil
import glob
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_dir_size(path):
    """Get directory size in human-readable format."""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
    except OSError:
        pass
    for unit in ['B', 'KB', 'MB', 'GB']:
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} TB"


def get_file_size(path):
    """Get file size in human-readable format."""
    try:
        size = os.path.getsize(path)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
    except OSError:
        return "0 B"


def cleanup_browser_profiles(dry_run=False):
    """清理浏览器配置文件目录 (browser_profiles/)"""
    profiles_dir = os.path.join(BASE_DIR, 'browser_profiles')
    if not os.path.exists(profiles_dir):
        print("  ✅ browser_profiles/ 目录不存在，无需清理")
        return 0
    
    size = get_dir_size(profiles_dir)
    platforms = [d for d in os.listdir(profiles_dir) if os.path.isdir(os.path.join(profiles_dir, d))]
    
    if not platforms:
        print("  ✅ browser_profiles/ 目录为空，无需清理")
        return 0
    
    print(f"  📁 browser_profiles/ ({size})")
    for platform in platforms:
        platform_path = os.path.join(profiles_dir, platform)
        platform_size = get_dir_size(platform_path)
        print(f"    └── {platform}/ ({platform_size})")
    
    if not dry_run:
        shutil.rmtree(profiles_dir)
        print("  🗑️  已删除 browser_profiles/")
    return 1


def cleanup_database(dry_run=False):
    """清理数据库文件 (instance/)"""
    instance_dir = os.path.join(BASE_DIR, 'instance')
    if not os.path.exists(instance_dir):
        print("  ✅ instance/ 目录不存在，无需清理")
        return 0
    
    db_files = glob.glob(os.path.join(instance_dir, '*.db')) + \
               glob.glob(os.path.join(instance_dir, '*.sqlite'))
    
    if not db_files:
        print("  ✅ 没有找到数据库文件")
        return 0
    
    for db_file in db_files:
        size = get_file_size(db_file)
        print(f"  📄 {os.path.relpath(db_file, BASE_DIR)} ({size})")
        if not dry_run:
            os.remove(db_file)
            print(f"    🗑️  已删除")
    return len(db_files)


def cleanup_cache(dry_run=False):
    """清理 Python 缓存文件 (__pycache__/)"""
    cache_dirs = []
    for root, dirs, files in os.walk(BASE_DIR):
        for d in dirs:
            if d == '__pycache__':
                cache_dirs.append(os.path.join(root, d))
    
    # Also find .pyc files outside __pycache__
    pyc_files = glob.glob(os.path.join(BASE_DIR, '**/*.pyc'), recursive=True)
    
    if not cache_dirs and not pyc_files:
        print("  ✅ 没有 Python 缓存文件")
        return 0
    
    count = 0
    for cache_dir in cache_dirs:
        size = get_dir_size(cache_dir)
        rel_path = os.path.relpath(cache_dir, BASE_DIR)
        print(f"  📁 {rel_path}/ ({size})")
        if not dry_run:
            shutil.rmtree(cache_dir)
        count += 1
    
    for pyc in pyc_files:
        rel_path = os.path.relpath(pyc, BASE_DIR)
        size = get_file_size(pyc)
        print(f"  📄 {rel_path} ({size})")
        if not dry_run:
            os.remove(pyc)
        count += 1
    
    if not dry_run:
        print(f"  🗑️  已清理 {count} 个缓存项")
    return count


def cleanup_logs(dry_run=False):
    """清理日志文件 (*.log)"""
    log_files = glob.glob(os.path.join(BASE_DIR, '*.log')) + \
                glob.glob(os.path.join(BASE_DIR, 'logs', '*.log'))
    
    if not log_files:
        print("  ✅ 没有日志文件")
        return 0
    
    for log_file in log_files:
        size = get_file_size(log_file)
        rel_path = os.path.relpath(log_file, BASE_DIR)
        print(f"  📄 {rel_path} ({size})")
        if not dry_run:
            os.remove(log_file)
    
    if not dry_run:
        print(f"  🗑️  已删除 {len(log_files)} 个日志文件")
    return len(log_files)


def cleanup_nohup(dry_run=False):
    """清理 nohup 输出文件"""
    nohup_files = glob.glob(os.path.join(BASE_DIR, 'nohup.out'))
    if not nohup_files:
        print("  ✅ 没有 nohup.out 文件")
        return 0
    for f in nohup_files:
        size = get_file_size(f)
        print(f"  📄 nohup.out ({size})")
        if not dry_run:
            os.remove(f)
    return len(nohup_files)


def main():
    parser = argparse.ArgumentParser(description='FindJob 临时文件清理工具')
    parser.add_argument('--all', action='store_true', help='清理所有临时文件')
    parser.add_argument('--browser', action='store_true', help='清理浏览器配置文件')
    parser.add_argument('--db', action='store_true', help='清理数据库文件')
    parser.add_argument('--cache', action='store_true', help='清理 Python 缓存')
    parser.add_argument('--log', action='store_true', help='清理日志文件')
    parser.add_argument('--nohup', action='store_true', help='清理 nohup.out')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际删除')
    
    args = parser.parse_args()
    
    # If no specific flag, run interactive mode
    no_flag = not any([args.all, args.browser, args.db, args.cache, args.log, args.nohup])
    
    print()
    print("🧹 FindJob 临时文件清理工具")
    print("=" * 40)
    
    if args.dry_run:
        print("⚠️  预览模式 (不会实际删除)")
        print()
    
    total_cleaned = 0
    
    if args.all or args.browser or no_flag:
        if no_flag and not args.all:
            print("\n[1/5] 浏览器配置文件 (browser_profiles/)")
            print("  包含各平台的浏览器 Cookie、Session 等登录数据")
            print("  ⚠️  清除后需要重新登录所有平台")
        else:
            print("\n[清理] 浏览器配置文件 (browser_profiles/)")
        total_cleaned += cleanup_browser_profiles(dry_run=args.dry_run)
    
    if args.all or args.db or no_flag:
        if no_flag and not args.all:
            print("\n[2/5] 数据库文件 (instance/)")
            print("  包含用户账号、平台凭证、消息记录等")
            print("  ⚠️  清除后所有数据将丢失")
        else:
            print("\n[清理] 数据库文件 (instance/)")
        total_cleaned += cleanup_database(dry_run=args.dry_run)
    
    if args.all or args.cache or no_flag:
        if no_flag and not args.all:
            print("\n[3/5] Python 缓存 (__pycache__/)")
            print("  编译的 .pyc 字节码缓存文件")
        else:
            print("\n[清理] Python 缓存")
        total_cleaned += cleanup_cache(dry_run=args.dry_run)
    
    if args.all or args.log or no_flag:
        if no_flag and not args.all:
            print("\n[4/5] 日志文件 (*.log)")
        else:
            print("\n[清理] 日志文件")
        total_cleaned += cleanup_logs(dry_run=args.dry_run)
    
    if args.all or args.nohup or no_flag:
        if no_flag and not args.all:
            print("\n[5/5] nohup 输出 (nohup.out)")
        else:
            print("\n[清理] nohup 输出")
        total_cleaned += cleanup_nohup(dry_run=args.dry_run)
    
    print()
    print("=" * 40)
    if args.dry_run:
        print(f"📋 预览完成，共发现 {total_cleaned} 项可清理")
        print("   运行 `python cleanup.py` 执行实际清理")
    else:
        if total_cleaned > 0:
            print(f"✅ 清理完成，共清理 {total_cleaned} 项")
        else:
            print("✅ 没有需要清理的临时文件")
    
    # Interactive mode: ask user to choose
    if no_flag and not args.all and not args.dry_run and total_cleaned == 0:
        pass  # nothing to do
    elif no_flag and not args.all and not args.dry_run:
        print()
        choice = input("是否清理以上所有项目? (y/N): ").strip().lower()
        if choice == 'y':
            print("\n🧹 开始清理...")
            cleanup_browser_profiles()
            cleanup_database()
            cleanup_cache()
            cleanup_logs()
            cleanup_nohup()
            print("\n✅ 清理完成!")
        else:
            print("已取消。")
            print("提示: 使用 `python cleanup.py --browser` 可以只清理浏览器配置")
    
    print()


if __name__ == '__main__':
    main()