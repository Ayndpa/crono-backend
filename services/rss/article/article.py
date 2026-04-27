from datetime import datetime, timezone
from sqlite3 import Connection
from fastapi import HTTPException
from models.rss.article import Article, ArticleResponse, ArticleState

def create_article(
    db: Connection,
    article: Article
) -> dict:
    """
    同时创建文章元数据、内容和状态记录。
    """
    try:
        # 开启事务
        db.execute("BEGIN")
        
        # 创建文章元数据
        cursor = db.cursor()
        sql_article = """
        INSERT INTO articles (
            feed_id, title, link, guid, pub_date, author
        ) VALUES (?, ?, ?, ?, ?, ?)
        """
        data_article = (
            article.feed_id,
            article.title,
            str(article.link),
            article.guid,
            article.pub_date.isoformat(),
            article.author,
        )
        try:
            cursor.execute(sql_article, data_article)
            article_id = cursor.lastrowid
        except Exception:
            raise HTTPException(status_code=400, detail="文章已存在，无法重复创建")
        
        # 初始化并设置关联的 article_state
        sql_state = """
        INSERT INTO article_states (article_id, is_read, tags, ai_summary, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """
        data_state = (
            article_id,
            False,
            "",
            None,
            datetime.now(timezone.utc),
        )
        cursor.execute(sql_state, data_state)

        # 提交事务
        db.commit()
        return {"detail": "文章创建成功", "article_id": article_id}
    except Exception as e:
        # 回滚事务
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建文章失败: {e}")

def delete_all_articles_and_related_data(db: Connection) -> dict:
    """
    删除所有文章及其相关的内容和状态记录。
    """
    try:
        # 开启事务
        db.execute("BEGIN")
        
        # 删除 article_states 表中的所有记录
        db.execute("DELETE FROM article_states")
        
        # 删除 article_contents 表中的所有记录
        db.execute("DELETE FROM article_contents")
        
        # 删除 articles 表中的所有记录
        db.execute("DELETE FROM articles")
        
        # 提交事务
        db.commit()
        return {"detail": "所有文章及相关数据已成功删除"}
    except Exception as e:
        # 回滚事务
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除文章失败: {e}")

def get_articles(db: Connection, user_id: int, feed_id: int = None, limit: int = 50) -> list[ArticleResponse]:
    """
    获取文章及其状态，按发布时间最新排序。
    通过 rss_feeds.user_id 过滤当前用户的文章。
    如果提供 feed_id，则仅返回该 feed_id 的文章；否则返回最新的文章。
    """
    try:
        cursor = db.cursor()
        sql = """
        SELECT 
            a.id, a.feed_id, a.title, a.link, a.guid, a.pub_date, a.author,
            s.is_read, s.tags, s.ai_summary, s.updated_at
        FROM articles a
        JOIN rss_feeds f ON a.feed_id = f.id
        LEFT JOIN article_states s ON a.id = s.article_id
        WHERE f.user_id = ?
        """
        if feed_id is not None:
            sql += """
            AND a.feed_id = ?
            ORDER BY a.pub_date DESC
            LIMIT ?
            """
            cursor.execute(sql, (user_id, feed_id, limit))
        else:
            sql += """
            ORDER BY a.pub_date DESC
            LIMIT ?
            """
            cursor.execute(sql, (user_id, limit))
        
        rows = cursor.fetchall()

        articles = [
            ArticleResponse(
                id=row[0],
                feed_id=row[1],
                title=row[2],
                link=row[3],
                guid=row[4],
                pub_date=row[5],
                author=row[6],
                is_read=row[7],
                tags=row[8].split(",") if row[8] else [],
                ai_summary=row[9],
                updated_at=row[10],
            )
            for row in rows
        ]
        return articles
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文章失败: {e}")