import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { sdk } from "../sdk";
import type { Category } from "../articles_sdk/resources.js";

export default function CategoryList() {
  const qc = useQueryClient();
  const [name, setName] = useState("");

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: async () => {
      const col = sdk.categories.list();
      await col.fetch();
      return [...col];
    },
  });

  const createMut = useMutation({
    mutationFn: (n: string) => sdk.categories.create({ name: n }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["categories"] });
      setName("");
    },
  });

  const deleteMut = useMutation({
    mutationFn: async (cat: Category) => {
      await cat.delete();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["categories"] }),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createMut.mutate(name.trim());
  };

  if (categories.isLoading)
    return <div className="p-6 text-slate-500">Loading…</div>;
  if (categories.error)
    return (
      <div className="p-6 text-red-600">
        {(categories.error as Error).message}
      </div>
    );

  return (
    <div className="p-6 max-w-lg">
      <h1 className="text-xl font-semibold text-slate-800 mb-4">Categories</h1>

      <form onSubmit={handleSubmit} className="flex gap-2 mb-6">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Category name"
          required
          className="flex-1 border border-slate-300 rounded-md px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={createMut.isPending}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {createMut.isPending ? "Adding…" : "Add"}
        </button>
      </form>

      {(categories.data ?? []).length === 0 ? (
        <div className="text-slate-500 text-sm text-center py-8">
          No categories yet.
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {(categories.data ?? []).map((cat) => (
                <tr key={cat.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-800">{cat.name}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {new Date(cat.created_at ?? "").toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => {
                        if (window.confirm(`Delete category "${cat.name}"?`))
                          deleteMut.mutate(cat);
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
      )}
    </div>
  );
}
