from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field

class Article(BaseModel):
    """
    Pydantic模型，用于表示RSS文章信息。
    """
    id: Optional[int] = Field(None, description="数据库内部的唯一标识符，自增")
    feed_id: int = Field(..., description="指向该文章所属 RSS Feed 的外键")
    title: str = Field(..., description="文章标题，例如 朝圣者 (Pilgrims)")
    link: HttpUrl = Field(..., description="文章的永久链接，用于访问原文")
    guid: str = Field(..., description="唯一标识符，用于判断文章是否已经存在，非常重要")
    pub_date: datetime = Field(..., description="文章发布时间，用于排序和显示")
    author: Optional[str] = Field(None, description="文章作者，例如 Amanita Design s.r.o.")

class ArticleState(BaseModel):
    """
    Pydantic模型，用于表示用户对文章的状态和标签。
    """
    article_id: Optional[int] = Field(None, description="关联的文章ID，可以稍后设置值")
    is_read: bool = Field(False, description="用户是否已读该文章")
    tags: Optional[list[str]] = Field(default_factory=list, description="对文章的分类或标签")
    ai_summary: Optional[str] = Field(None, description="AI生成的文章总结内容")
    ai_translation: Optional[str] = Field(None, description="AI生成的全文翻译")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="状态最后更新时间")

class ArticleResponse(BaseModel):
    """
    Pydantic模型，用于返回完整的文章信息，包括状态。
    """
    id: Optional[int] = Field(None, description="数据库内部的唯一标识符，自增")
    feed_id: int = Field(..., description="指向该文章所属 RSS Feed 的外键")
    title: str = Field(..., description="文章标题，例如 朝圣者 (Pilgrims)")
    link: HttpUrl = Field(..., description="文章的永久链接，用于访问原文")
    guid: str = Field(..., description="唯一标识符，用于判断文章是否已经存在，非常重要")
    pub_date: datetime = Field(..., description="文章发布时间，用于排序和显示")
    author: Optional[str] = Field(None, description="文章作者，例如 Amanita Design s.r.o.")
    is_read: bool = Field(False, description="用户是否已读该文章")
    tags: Optional[list[str]] = Field(default_factory=list, description="对文章的分类或标签")
    ai_summary: Optional[str] = Field(None, description="AI生成的文章总结内容")
    ai_translation: Optional[str] = Field(None, description="AI生成的全文翻译")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="状态最后更新时间")
