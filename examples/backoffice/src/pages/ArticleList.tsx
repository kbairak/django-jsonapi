import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { sdk } from "../sdk";

export default function ArticleList() {
  const [page, setPage] = useState(1);
  const [titleSearch, setTitleSearch] = useState("");
  const qc = useQueryClient();

  const articles = useQuery({
    queryKey: ["articles", page, titleSearch],
    queryFn: async () => {
      let col = sdk.articles
        .list()
        .page({ number: String(page), size: "10" });
      if (titleSearch) col = col.filter({ title__contains: titleSearch });
      await col.fetch();
      return {
        items: [...col],
        hasNext: col.hasNext(),
        hasPrev: col.hasPrevious(),
        total: col.meta.total as number,
      };
    },
    placeholderData: (prev) => prev,
  });

  const del = useMutation({
    mutationFn: async (id: number) => {
      const a = await sdk.articles.get(String(id));
      await a.delete();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["articles"] }),
  });

  const publishMut = useMutation({
    mutationFn: async (id: number) => {
      const a = await sdk.articles.get(String(id));
      await a.rpc('publish');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["articles"] }),
  });

  if (articles.isPending)
    return <div className="p-6 text-slate-500">Loading…</div>;
  if (articles.error)
    return (
      <div className="p-6 text-red-600">
        {(articles.error as Error).message}
      </div>
    );
  if (!articles.data) return null;

  const { items, hasNext, hasPrev, total } = articles.data;
  const totalPages = Math.max(1, Math.ceil(total / 10));

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-slate-800">Articles</h1>
        <Link
          to="/articles/new"
          className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700"
        >
          New Article
        </Link>
      </div>

      <div className="mb-4">
        <input
          type="text"
          value={titleSearch}
          onChange={(e) => {
            setTitleSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Search by title…"
          className="w-full max-w-xs border border-slate-300 rounded-md px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        />
      </div>

      {items.length === 0 ? (
        <div className="text-slate-500 text-sm py-8 text-center">
          No articles yet.
        </div>
      ) : (
        <>
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-left">
                <tr>
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Author</th>
                  <th className="px-4 py-3 font-medium">Published</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {items.map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link
                        to={`/articles/${a.id}`}
                        className="text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        {a.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {a.author?.id ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {a.published ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          Published
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                          Draft
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">
                      {new Date(a.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/articles/${a.id}`}
                        className="text-indigo-600 hover:text-indigo-800 text-xs font-medium mr-3"
                      >
                        Edit
                      </Link>
                      {!a.published && (
                        <button
                          onClick={() => {
                            if (window.confirm(`Publish "${a.title}"?`))
                              publishMut.mutate(Number(a.id));
                          }}
                          className="text-green-600 hover:text-green-800 text-xs font-medium mr-3"
                        >
                          Publish
                        </button>
                      )}
                      <button
                        onClick={() => {
                          if (window.confirm(`Delete "${a.title}"?`))
                            del.mutate(Number(a.id));
                        }}
                        className="text-red-600 hover:text-red-800 text-xs font-medium"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-center gap-3 mt-4 text-sm">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={!hasPrev}
              className="px-3 py-1.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-slate-600">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={!hasNext}
              className="px-3 py-1.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
