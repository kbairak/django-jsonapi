import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate, Link } from "react-router-dom";
import { sdk } from "../sdk";
import type { ArticleCreate, ArticleEdit } from "../articles_sdk/resources.js";

function formatDate(d: string | null | undefined): string {
  if (!d) return "";
  return new Date(d).toLocaleDateString();
}

export default function ArticleForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isEdit = !!id;

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [authorId, setAuthorId] = useState<number | "">("");
  const [categoryIds, setCategoryIds] = useState<Set<number>>(new Set());

  const article = useQuery({
    queryKey: ["articles", id],
    queryFn: () => sdk.articles.get(id!),
    enabled: isEdit,
  });

  const publishMut = useMutation({
    mutationFn: async () => {
      const a = await sdk.articles.get(id!);
      await a.rpc('publish');
      return a;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["articles"] }),
  });

  useEffect(() => {
    if (article.data) {
      setTitle(article.data.title ?? "");
      setContent(article.data.content ?? "");
      setAuthorId(
        article.data.author?.id ? Number(article.data.author.id) : "",
      );
      const cats = article.data.categories;
      if (cats) {
        setCategoryIds(new Set([...cats].map((c) => Number(c.id))));
      }
    }
  }, [article.data]);

  const users = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const col = sdk.users.list();
      await col.fetch();
      return [...col];
    },
  });

  const allCategories = useQuery({
    queryKey: ["categories"],
    queryFn: async () => {
      const col = sdk.categories.list();
      await col.fetch();
      return [...col];
    },
  });

  const toggleCategory = (catId: number) => {
    setCategoryIds((prev) => {
      const next = new Set(prev);
      if (next.has(catId)) next.delete(catId);
      else next.add(catId);
      return next;
    });
  };

  const createMut = useMutation({
    mutationFn: (data: ArticleCreate) =>
      sdk.articles.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["articles"] });
      navigate("/articles");
    },
  });

  const updateMut = useMutation({
    mutationFn: async (data: ArticleEdit) => {
      const a = await sdk.articles.get(id!);
      await a.save(data);
      return a;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["articles"] });
      navigate("/articles");
    },
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim() || authorId === "") return;

    if (isEdit) {
      await updateMut.mutateAsync({
        title: title.trim(),
        content: content.trim(),
        author: Number(authorId),
      });
      const a = await sdk.articles.get(id!);
      const existingIds = new Set(
        a.categories ? [...a.categories].map((c) => Number(c.id)) : [],
      );
      const toAdd = [...categoryIds].filter((cid) => !existingIds.has(cid));
      const toRemove = [...existingIds].filter((cid) => !categoryIds.has(cid));
      if (toAdd.length) await a.add("categories", ...toAdd);
      if (toRemove.length) await a.remove("categories", ...toRemove);
    } else {
      createMut.mutate({
        title: title.trim(),
        content: content.trim(),
        author: Number(authorId),
        categories: [...categoryIds],
      });
    }
  };

  const error = createMut.error ?? updateMut.error;

  if (isEdit && article.isLoading)
    return <div className="p-6 text-slate-500">Loading…</div>;

  return (
    <div className="p-6 max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <Link to="/articles" className="text-slate-400 hover:text-slate-600">
          &larr; Back
        </Link>
        <h1 className="text-xl font-semibold text-slate-800">
          {isEdit ? "Edit Article" : "New Article"}
        </h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Title
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Content
          </label>
          <textarea
            rows={6}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            required
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Author
          </label>
          <select
            value={authorId}
            onChange={(e) =>
              setAuthorId(e.target.value ? Number(e.target.value) : "")
            }
            required
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          >
            <option value="">Select an author</option>
            {(users.data ?? []).map((u) => (
              <option key={u.id} value={u.id ?? ""}>
                {u.username}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Categories
          </label>
          <div className="flex flex-wrap gap-2">
            {(allCategories.data ?? []).length === 0 ? (
              <span className="text-sm text-slate-400">No categories available</span>
            ) : (
              (allCategories.data ?? []).map((cat) => {
                const checked = categoryIds.has(Number(cat.id));
                return (
                  <label
                    key={cat.id}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border cursor-pointer transition-colors ${
                      checked
                        ? "bg-indigo-100 text-indigo-700 border-indigo-300"
                        : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleCategory(Number(cat.id))}
                      className="sr-only"
                    />
                    {cat.name}
                  </label>
                );
              })
            )}
          </div>
        </div>

        {isEdit && article.data && (
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <span>Created: {formatDate(article.data.created_at)}</span>
            <span>
              Status:{" "}
              {article.data.published ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                  Published
                </span>
              ) : (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                  Draft
                </span>
              )}
            </span>
          </div>
        )}

        {error && (
          <div className="text-red-600 text-sm">{(error as Error).message}</div>
        )}

        {isEdit && article.data && !article.data.published && (
          <div className="pt-2">
            <button
              type="button"
              disabled={publishMut.isPending}
              onClick={() => publishMut.mutate()}
              className="bg-green-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {publishMut.isPending ? "Publishing…" : "Publish"}
            </button>
          </div>
        )}

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={createMut.isPending || updateMut.isPending}
            className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {createMut.isPending || updateMut.isPending ? "Saving…" : "Save"}
          </button>
          <Link
            to="/articles"
            className="text-sm text-slate-600 hover:text-slate-800"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
