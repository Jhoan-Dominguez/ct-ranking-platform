"""Foros de discusión: publicaciones, comentarios y "me gusta"."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Comment, Post, PostLike, User

CATEGORIES = [
    "General",
    "Duda académica",
    "Problemática",
    "Proyecto",
    "Recursos",
    "Vida universitaria",
]
ORDERINGS = {"Más recientes": "recent", "Más comentadas": "comments", "Más valoradas": "likes"}


class ForumError(ValueError):
    pass


@dataclass
class PostRow:
    post: Post
    comments: int
    likes: int


def create_post(
    session: Session, author_id: int, *, title: str, body: str, category: str, tags: str = ""
) -> Post:
    title, body = title.strip(), body.strip()
    if len(title) < 5:
        raise ForumError("El título debe tener al menos 5 caracteres.")
    if len(title) > 200:
        raise ForumError("El título supera 200 caracteres.")
    if not body:
        raise ForumError("La publicación necesita contenido.")
    if category not in CATEGORIES:
        raise ForumError("Categoría inválida.")
    clean_tags = ",".join(t.strip().lower() for t in tags.split(",") if t.strip())[:200]
    post = Post(author_id=author_id, title=title, body=body, category=category, tags=clean_tags)
    session.add(post)
    session.flush()
    return post


def list_posts(
    session: Session,
    *,
    search: str = "",
    category: str | None = None,
    solved: bool | None = None,
    author_ids: set[int] | None = None,
    order: str = "recent",
    limit: int = 100,
) -> list[PostRow]:
    n_comments = select(func.count(Comment.id)).where(Comment.post_id == Post.id).scalar_subquery()
    n_likes = select(func.count()).where(PostLike.post_id == Post.id).scalar_subquery()
    stmt = select(Post, n_comments.label("c"), n_likes.label("l")).options(
        selectinload(Post.author)
    )
    if search.strip():
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Post.title).like(like),
                func.lower(Post.body).like(like),
                func.lower(Post.tags).like(like),
            )
        )
    if category:
        stmt = stmt.where(Post.category == category)
    if solved is not None:
        stmt = stmt.where(Post.is_solved.is_(solved))
    if author_ids is not None:
        stmt = stmt.where(Post.author_id.in_(author_ids))
    order_by = {
        "comments": (n_comments.desc(), Post.created_at.desc()),
        "likes": (n_likes.desc(), Post.created_at.desc()),
    }.get(order, (Post.created_at.desc(),))
    stmt = stmt.order_by(*order_by).limit(limit)
    return [PostRow(post=p, comments=c, likes=lk) for p, c, lk in session.execute(stmt)]


def get_post(session: Session, post_id: int) -> Post | None:
    stmt = (
        select(Post)
        .where(Post.id == post_id)
        .options(
            selectinload(Post.author),
            selectinload(Post.comments).selectinload(Comment.author),
            selectinload(Post.likes),
        )
    )
    return session.scalar(stmt)


def add_comment(session: Session, post_id: int, author_id: int, body: str) -> Comment:
    body = body.strip()
    if not body:
        raise ForumError("El comentario está vacío.")
    if len(body) > 5000:
        raise ForumError("El comentario es demasiado largo.")
    if session.get(Post, post_id) is None:
        raise ForumError("La publicación no existe.")
    comment = Comment(post_id=post_id, author_id=author_id, body=body)
    session.add(comment)
    session.flush()
    return comment


def _can_moderate(actor: User, owner_id: int) -> bool:
    return actor.is_admin or actor.id == owner_id


def delete_post(session: Session, actor: User, post_id: int) -> None:
    post = session.get(Post, post_id)
    if post is None:
        return
    if not _can_moderate(actor, post.author_id):
        raise ForumError("Sólo el autor o un administrador puede eliminar la publicación.")
    session.delete(post)


def delete_comment(session: Session, actor: User, comment_id: int) -> None:
    comment = session.get(Comment, comment_id)
    if comment is None:
        return
    if not _can_moderate(actor, comment.author_id):
        raise ForumError("Sólo el autor o un administrador puede eliminar el comentario.")
    session.delete(comment)


def set_solved(session: Session, actor: User, post_id: int, solved: bool) -> None:
    post = session.get(Post, post_id)
    if post is None:
        raise ForumError("La publicación no existe.")
    if not _can_moderate(actor, post.author_id):
        raise ForumError("Sólo el autor puede marcar la publicación como resuelta.")
    post.is_solved = solved


def toggle_like(session: Session, post_id: int, user_id: int) -> bool:
    """Devuelve True si quedó con "me gusta"."""
    like = session.get(PostLike, (post_id, user_id))
    if like is not None:
        session.delete(like)
        return False
    session.add(PostLike(post_id=post_id, user_id=user_id))
    session.flush()
    return True
