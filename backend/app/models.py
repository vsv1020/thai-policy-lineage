# -*- coding: utf-8 -*-
"""SQLAlchemy 2.0 模型。

设计要点:
- 词表(领域/机关/法律形式/工具/目标/…)是**真表**,不是枚举字符串 —— 外键约束顶替了
  tools/validate.py 里的词表校验,写入时数据库自己就会拒绝未知 id。
- 多值字段(机关、领域、工具、目标、作用对象)全部走关联表,而不是 JSON 列 ——
  维度五「机构联署」和维度二「工具×目标」都是关联表上的 GROUP BY,不需要在应用层展开。
- 日期仍是四个独立列:决议 / 刊登 / 生效起止 / 意见截止。这是「决议已过、公报未刊、
  尚未生效」三态并存的唯一表达方式,也是「待刊公报」预警的查询条件。
- 兼容 SQLite 与 PostgreSQL:不用任何方言专属类型。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────── 词表 ───────────────────────────

class Domain(Base):
    __tablename__ = "domains"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))
    th: Mapped[str] = mapped_column(String(128), default="")
    en: Mapped[str] = mapped_column(String(128), default="")
    chip: Mapped[str] = mapped_column(String(32), default="")


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))
    th: Mapped[str] = mapped_column(String(128), default="")
    abbr: Mapped[str] = mapped_column(String(32), default="")
    ministry: Mapped[str | None] = mapped_column(String(32), nullable=True)


class LegalForm(Base):
    __tablename__ = "legal_forms"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))
    th: Mapped[str] = mapped_column(String(128), default="")
    abbr: Mapped[str] = mapped_column(String(64), default="")
    # 1–5,越大越稳定(法律 > 公告)。维度三整页就是这一列的分布
    stability: Mapped[int] = mapped_column(Integer, default=1)
    justiciable: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(255), default="")


class Status(Base):
    __tablename__ = "statuses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))
    pill: Mapped[str] = mapped_column(String(32), default="")
    in_force: Mapped[bool] = mapped_column(Boolean, default=False)


class InstrumentClass(Base):
    __tablename__ = "instrument_classes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))
    desc: Mapped[str] = mapped_column(String(128), default="")
    color: Mapped[str] = mapped_column(String(32), default="")


class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))
    class_id: Mapped[str] = mapped_column(ForeignKey("instrument_classes.id"))
    klass: Mapped[InstrumentClass] = relationship()


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))


class ImplementationStage(Base):
    __tablename__ = "implementation_stages"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer, default=0)


class Party(Base):
    __tablename__ = "parties"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    zh: Mapped[str] = mapped_column(String(64))


# ─────────────────────────── 事实 ───────────────────────────

class Issue(Base):
    """议题 —— 把多份文件串成一条演进脉络。"""
    __tablename__ = "issues"
    issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title_zh: Mapped[str] = mapped_column(String(255))
    title_th: Mapped[str] = mapped_column(String(255), default="")
    summary_zh: Mapped[str] = mapped_column(Text, default="")
    watch: Mapped[str] = mapped_column(Text, default="")
    domains_csv: Mapped[str] = mapped_column(String(255), default="")
    stages_json: Mapped[str] = mapped_column(Text, default="[]")   # 顺序敏感,整体存


class Document(Base):
    __tablename__ = "documents"
    uid: Mapped[str] = mapped_column(String(96), primary_key=True)
    issue_id: Mapped[str | None] = mapped_column(ForeignKey("issues.issue_id"), nullable=True)

    title_zh: Mapped[str] = mapped_column(String(512))
    title_th: Mapped[str] = mapped_column(String(512), default="")
    title_en: Mapped[str] = mapped_column(String(512), default="")
    summary_zh: Mapped[str] = mapped_column(Text, default="")

    legal_form_id: Mapped[str] = mapped_column(ForeignKey("legal_forms.id"))
    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"))
    implementation_stage_id: Mapped[str | None] = mapped_column(
        ForeignKey("implementation_stages.id"), nullable=True)

    direction: Mapped[str] = mapped_column(String(16), default="neutral")
    direction_confidence: Mapped[str] = mapped_column(String(8), default="none")
    direction_method: Mapped[str] = mapped_column(String(16), default="manual")

    doc_no: Mapped[str] = mapped_column(String(128), default="")
    gazette_series: Mapped[str] = mapped_column(String(8), default="")
    gazette_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gazette_part: Mapped[str] = mapped_column(String(32), default="")

    # 四类日期分开存 —— 见模块 docstring
    resolved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    comment_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 排序与按月聚合用的展示日期(刊登→决议→生效→意见截止 取第一个有值的)
    display_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    pipeline: Mapped[str] = mapped_column(String(32), default="manual")
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[str] = mapped_column(String(32), default="")
    confidence_dates: Mapped[str] = mapped_column(String(8), default="none")
    confidence_doc_no: Mapped[str] = mapped_column(String(8), default="none")

    subjects_csv: Mapped[str] = mapped_column(String(512), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    has_detail_page: Mapped[bool] = mapped_column(Boolean, default=False)

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    legal_form: Mapped[LegalForm] = relationship(lazy="joined")
    status: Mapped[Status] = relationship(lazy="joined")
    agencies: Mapped[list["DocumentAgency"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")
    domains: Mapped[list["DocumentDomain"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")
    instruments: Mapped[list["DocumentInstrument"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")
    goals: Mapped[list["DocumentGoal"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")
    parties: Mapped[list["DocumentParty"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")
    sources: Mapped[list["DocumentSource"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")
    relations_out: Mapped[list["DocumentRelation"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin",
        foreign_keys="DocumentRelation.src_uid")


class DocumentAgency(Base):
    """联署关系。维度五的机构协同 = 这张表自连接后按机关对计数。"""
    __tablename__ = "document_agencies"
    __table_args__ = (UniqueConstraint("uid", "agency_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(ForeignKey("documents.uid", ondelete="CASCADE"), index=True)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)   # 0 = 主办机关


class DocumentDomain(Base):
    __tablename__ = "document_domains"
    __table_args__ = (UniqueConstraint("uid", "domain_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(ForeignKey("documents.uid", ondelete="CASCADE"), index=True)
    domain_id: Mapped[str] = mapped_column(ForeignKey("domains.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)   # 0 = 主领域(决定 chip 配色)


class DocumentInstrument(Base):
    __tablename__ = "document_instruments"
    __table_args__ = (UniqueConstraint("uid", "instrument_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(ForeignKey("documents.uid", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)


class DocumentGoal(Base):
    __tablename__ = "document_goals"
    __table_args__ = (UniqueConstraint("uid", "goal_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(ForeignKey("documents.uid", ondelete="CASCADE"), index=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), index=True)


class DocumentParty(Base):
    """维度四:谁被支持、谁被约束。"""
    __tablename__ = "document_parties"
    __table_args__ = (UniqueConstraint("uid", "party_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(ForeignKey("documents.uid", ondelete="CASCADE"), index=True)
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), index=True)
    stance: Mapped[str] = mapped_column(String(16), default="neutral")


class DocumentSource(Base):
    __tablename__ = "document_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(ForeignKey("documents.uid", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="secondary")
    url: Mapped[str] = mapped_column(String(1024), default="")
    note: Mapped[str] = mapped_column(String(512), default="")


class DocumentRelation(Base):
    """替代/修订/落实/废止…。写入时成对写,前端画脉络图直接读边表。"""
    __tablename__ = "document_relations"
    __table_args__ = (UniqueConstraint("src_uid", "type", "dst_uid"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src_uid: Mapped[str] = mapped_column(ForeignKey("documents.uid", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    dst_uid: Mapped[str] = mapped_column(String(96), index=True)


class Conflict(Base):
    """维度六:同一事项在不同文件里口径不一致。"""
    __tablename__ = "conflicts"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    severity: Mapped[str] = mapped_column(String(8), default="med")
    title_zh: Mapped[str] = mapped_column(String(512))
    domains_csv: Mapped[str] = mapped_column(String(255), default="")
    impact_zh: Mapped[str] = mapped_column(Text, default="")
    detected_by: Mapped[str] = mapped_column(String(64), default="manual")
    confidence: Mapped[str] = mapped_column(String(8), default="med")
    sides_json: Mapped[str] = mapped_column(Text, default="[]")


class Deadline(Base):
    """周期性法定截止日(报税、年度备案)—— 与文件生效日是不同实体。"""
    __tablename__ = "deadlines"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title_zh: Mapped[str] = mapped_column(String(255))
    domains_csv: Mapped[str] = mapped_column(String(255), default="")
    agencies_csv: Mapped[str] = mapped_column(String(255), default="")
    recurrence_json: Mapped[str] = mapped_column(Text, default="{}")
    note: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(8), default="med")


# ─────────────────────────── 运维 ───────────────────────────

class CollectRun(Base):
    """每次采集留一条记录 —— 「上次什么时候跑的、成没成、捞到几条」是产品要展示的信息。"""
    __tablename__ = "collect_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/ok/partial/failed
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual/schedule/api
    added: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str] = mapped_column(Text, default="")


class SourceHealth(Base):
    """每个数据源的最近状态,直接驱动页面右上角的「源 N/M 可用」。"""
    __tablename__ = "source_health"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(16), default="unattempted")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")


# ─────────────────────────── 站点统计 ───────────────────────────

class PageHit(Base):
    """第一方访问统计:一行一次浏览或一个事件。

    不用 Cookie、不存 IP。visitor 是 hash(密钥 · 当天日期 · IP · UA) 的前 16 位 ——
    密钥每天轮换,所以同一个人跨天无法关联,只能做「按天去重」的访客数。
    与事实层无关:不进 JSONL、不参与导出,ingest --reset 也不会清它。
    """
    __tablename__ = "page_hits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)            # 曼谷日期
    hour: Mapped[int] = mapped_column(Integer, default=0)          # 曼谷小时 0–23
    kind: Mapped[str] = mapped_column(String(8), default="pv")     # pv / event
    name: Mapped[str] = mapped_column(String(32), default="", index=True)  # 事件名
    path: Mapped[str] = mapped_column(String(255), default="")
    label: Mapped[str] = mapped_column(String(160), default="")
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visitor: Mapped[str] = mapped_column(String(16), default="", index=True)
    ref_host: Mapped[str] = mapped_column(String(128), default="")
    utm_source: Mapped[str] = mapped_column(String(64), default="")
    utm_medium: Mapped[str] = mapped_column(String(64), default="")
    utm_campaign: Mapped[str] = mapped_column(String(64), default="")
    device: Mapped[str] = mapped_column(String(8), default="")     # mobile / tablet / desktop
    lang: Mapped[str] = mapped_column(String(8), default="")
    country: Mapped[str] = mapped_column(String(2), default="")    # 仅在 Cloudflare 等代理提供时
