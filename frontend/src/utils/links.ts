// 文档站唯一出口：域名/路径改动只改这里，各处经 docsUrl() 拼深链（slug 带尾斜杠，如 'api/'）
export const DOCS_URL = 'https://nmail.whizzzest.com/docs/'

export const docsUrl = (slug = '') => `${DOCS_URL}${slug}`
