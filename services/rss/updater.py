import time
import os
from datetime import datetime, timezone
import schedule

# 导入自定义模块
from services.database import get_db
from services.rss.article.article import create_article
from services.rss.article.metadata import article_exists
from services.rss.request import get_rss_feed
from services.rss.feed import get_all_feeds
from models.rss.article import Article

class RSSUpdater:
    def __init__(self):
        self.interval = int(os.environ.get('RSS_READ_INTERVAL', '30'))  # 间隔时间（分钟），默认30
        self.running = True  # 控制任务运行状态
        self.auto_refresh = os.environ.get('RSS_AUTO_REFRESH', 'true').lower() == 'true'

    def safely_close_generator(self, generator):
        """
        安全关闭生成器，避免重复代码。
        """
        try:
            next(generator, None)
        except StopIteration:
            pass

    def process_feed_entry(self, conn, feed, entry):
        """
        处理单个 RSS 源条目。
        """
        guid = entry.get('guid', entry.get('link'))
        if not guid:
            print(f" - 警告: 文章缺少 'guid' 和 'link'，跳过此文章。标题: {entry.get('title', '未知')}")
            return 0

        if article_exists(conn, guid):
            return 0

        try:
            pub_date = datetime.fromtimestamp(
                time.mktime(entry.published_parsed), tz=timezone.utc
            ) if hasattr(entry, 'published_parsed') and entry.published_parsed else datetime.now(tz=timezone.utc)
        except (ValueError, TypeError):
            pub_date = datetime.now(tz=timezone.utc)

        try:
            article = Article(
                feed_id=feed.id,
                title=entry.title,
                link=entry.link,
                guid=guid,
                pub_date=pub_date,
                author=entry.get('author', None),
            )
            create_article(conn, article)
            return 1
        except Exception as e:
            print(f" - 警告: 无法创建或添加文章模型，跳过。错误: {e}")
            return 0

    def process_feed(self, conn, feed):
        """
        处理单个 RSS 源。
        """
        if not feed.is_active:
            print(f"-> 跳过未激活的 RSS 源 (id: {feed.id}, url: {feed.url})...")
            return 0

        print(f"-> 正在处理 RSS 源 (id: {feed.id}, url: {feed.url})...")
        feed_data = get_rss_feed(feed.url)
        if not feed_data or not hasattr(feed_data, 'entries'):
            print(f" - 警告: 无法获取或解析此RSS源，跳过。")
            return 0

        new_articles_count = sum(self.process_feed_entry(conn, feed, entry) for entry in feed_data.entries)
        print(f" - 成功添加了 {new_articles_count} 篇新文章。")
        return new_articles_count

    def check_and_update_feeds(self):
        """
        后台任务：检查并更新所有 RSS 源。
        """
        print(f"\n[{datetime.now().isoformat()}] 正在启动RSS源检查任务...")

        total_new_articles = 0
        db_generator = get_db()
        try:
            conn = next(db_generator)
            
            # 动态获取 RSS 源
            rss_feeds = get_all_feeds(conn)
            if not rss_feeds:
                print("警告: 没有可用的 RSS 源。")
                return
            
            total_new_articles = sum(self.process_feed(conn, feed) for feed in rss_feeds)
        except StopIteration:
            print("错误: get_db 生成器已耗尽。")
        except Exception as e:
            print(f"RSS更新任务发生致命错误: {e}")
        finally:
            self.safely_close_generator(db_generator)

        print(f"RSS源检查任务完成。共添加 {total_new_articles} 篇新文章。")

    def refresh_now(self):
        """
        外部调用：立即刷新 RSS 源。
        """
        print("外部调用：立即刷新 RSS 源...")
        self.check_and_update_feeds()

    def stop(self):
        """
        外部调用：终止定时任务。
        """
        print("外部调用：终止 RSS 更新程序...")
        self.running = False

    def start(self):
        """
        主函数，设置并运行定时任务。
        """
        # 首次运行时，立即执行一次
        self.check_and_update_feeds()

        if not self.auto_refresh:
            print("RSS更新程序已启动，但自动刷新功能已禁用。仅支持手动刷新。")
            return

        # 定义定时任务，使用配置的间隔时间
        schedule.every(self.interval).minutes.do(self.check_and_update_feeds)
        
        print("RSS更新程序已启动，任务将在后台运行。")
        print(f"首次任务已立即执行，后续任务将在{self.interval}分钟后执行。")

        while self.running:
            schedule.run_pending()
            time.sleep(1)

if __name__ == "__main__":
    updater = RSSUpdater()
    updater.start()