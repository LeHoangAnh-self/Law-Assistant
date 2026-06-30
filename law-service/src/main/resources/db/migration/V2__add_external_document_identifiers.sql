alter table legal_documents add column external_source varchar(255) null;
alter table legal_documents add column external_docid varchar(255) null;
alter table legal_documents add column source_url varchar(1000) null;

create index idx_legal_documents_external_docid
    on legal_documents (external_source, external_docid);
create index idx_legal_documents_scope on legal_documents (scope);
create index idx_legal_documents_authority on legal_documents (issuing_authority);
create index idx_legal_documents_effective_date on legal_documents (effective_date);
create index idx_legal_documents_expired_date on legal_documents (expired_date);
