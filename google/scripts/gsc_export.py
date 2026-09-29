import json
import os
import sys

import gsc_client

PERMISSION_LABELS = {
    "siteOwner": "✅ Владелец",
    "siteFullUser": "ℹ️ Полный доступ",
    "siteRestrictedUser": "⚠️ Ограниченный доступ",
    "siteUnverifiedUser": "❌ Не подтверждён",
}


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_export.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def parse_links(value):
    if isinstance(value, str):
        return [l.strip() for l in value.strip().split('\n') if l.strip()]
    if isinstance(value, list):
        return [str(l).strip() for l in value if str(l).strip()]
    return []


def sitemap_status(s):
    try:
        errors = int(s.get('errors') or 0)
    except (TypeError, ValueError):
        errors = 0
    if errors > 0:
        return 'error'
    if s.get('isPending'):
        return 'pending'
    return 'ok'


def sitemap_status_label(s, expected):
    correct = (s.get('path') or '') == expected
    if not correct:
        return "⚠️ Неправильный"
    status = sitemap_status(s)
    if status == 'error':
        return "❌ Ошибка"
    if status == 'pending':
        return "⏳ В обработке"
    return "✅ Успешно"


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = load_data()
    links = parse_links(data.get('links'))
    show_sitemaps = bool(data.get('show_sitemaps'))

    webmasters, _, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print(f"⚠️  {auth_info}")
        return

    print(f"ℹ️  Аккаунт: {auth_info}")
    print(f"ℹ️  Сайтмапы: {'включены' if show_sitemaps else 'выключены'}")
    if links:
        print(f"ℹ️  Сайтов для анализа: {len(links)}")

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    sites = sites_res.get('siteEntry', [])

    if links:
        matched = []
        seen = set()
        not_found = []
        for l in links:
            found = gsc_client.resolve_entries(sites, l)
            if not found:
                if l.strip() not in not_found:
                    not_found.append(l.strip())
                continue
            for e in found:
                k = gsc_client.property_key(e.get('siteUrl', ''))
                if k in seen:
                    continue
                seen.add(k)
                matched.append(e)
        sites = matched
        if not_found:
            print(f"ℹ️  Не найдены в GSC: {', '.join(not_found)}")

    total = len(sites)
    print(f"ℹ️  Сайтов анализируется: {total}")

    config = gsc_client.load_config()
    sitemap_path = str(config.get('sitemap_path') or '').strip()
    if show_sitemaps and not sitemap_path:
        print("❌ Для выгрузки сайтмапов нужен sitemap_path в настройках Google")
        return
    if not sitemap_path.startswith('/'):
        sitemap_path = '/' + sitemap_path

    limiter = gsc_client.rate_limiter()

    def process_site(entry, _idx=0):
        """Данные одного сайта: (cells, stats). Сетевой запрос — только при show_sitemaps."""
        site_url = entry.get('siteUrl', '')
        level = entry.get('permissionLevel', '')
        cells = [site_url, PERMISSION_LABELS.get(level, level)]
        stats = {"unverified": 0, "no_correct": 0, "wrong_sites": 0, "correct_bad": 0}

        if not show_sitemaps:
            return cells, stats

        if level == 'siteUnverifiedUser':
            stats["unverified"] = 1
            return cells + [["—"], ["—"]], stats

        try:
            sm_res = gsc_client.retry_on_quota(
                lambda: gsc_client.thread_webmasters().sitemaps().list(siteUrl=site_url).execute(),
                limiter)
        except Exception as e:
            return cells + [["—"], [f"❌ {gsc_client.api_error_str(e)}"]], stats

        sitemaps = sm_res.get('sitemap', [])
        expected = f"{site_url.rstrip('/')}{sitemap_path}"

        if not sitemaps:
            stats["no_correct"] = 1
            return cells + [["—"], ["—"]], stats

        correct_maps = [sm for sm in sitemaps if (sm.get('path') or '') == expected]
        if not correct_maps:
            stats["no_correct"] = 1
        if any((sm.get('path') or '') != expected for sm in sitemaps):
            stats["wrong_sites"] = 1
        if any(sitemap_status(sm) != 'ok' for sm in correct_maps):
            stats["correct_bad"] = 1

        paths = [sm.get('path', '') or '?' for sm in sitemaps]
        statuses = [sitemap_status_label(sm, expected) for sm in sitemaps]
        return cells + [paths, statuses], stats

    # Без чекбокса «Сайтмапы» запросов на сайт нет — пул не создаём.
    workers = 1 if not show_sitemaps else None
    if show_sitemaps and total > 1:
        print(f"ℹ️  Распараллеливание: потоков x{gsc_client.MAX_WORKERS}, "
              f"темп ~{gsc_client.RATE_LIMIT_RPS:.0f} запр./сек (квота Google — 20 QPS)")

    unverified = no_correct = wrong_sites = correct_bad = 0
    processed = 0

    for _idx, (cells, stats) in gsc_client.run_parallel(sites, process_site, max_workers=workers):
        processed += 1
        print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")
        unverified += stats["unverified"]
        no_correct += stats["no_correct"]
        wrong_sites += stats["wrong_sites"]
        correct_bad += stats["correct_bad"]

    summary = {"Сайтов": total, "Не подтверждённых": unverified}
    if show_sitemaps:
        summary["Без правильного сайтмапа"] = no_correct
        summary["С неправильными сайтмапами"] = wrong_sites
        summary["Правильный сайтмап с плохим статусом"] = correct_bad

    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()