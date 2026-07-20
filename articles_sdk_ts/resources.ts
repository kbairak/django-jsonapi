import { Collection } from "./_runtime/collection.js";
import { Resource } from "./_runtime/resource.js";

export interface ArticleQuery {
    title__contains?: string;
    category?: number | null;
}

export interface ArticleGetQuery {}

export interface ArticleEdit {
    title?: string | null;
    content?: string | null;
    author?: User | number | null;
}

export interface ArticleCreate {
    title?: string;
    content?: string;
    author?: User | number | null;
    categories?: (Category | number[])[] | null;
}

export interface UserQuery {
    username?: string;
}

export interface UserGetQuery {}

export interface CategoryQuery {
    article?: number | null;
}

export interface CategoryCreate {
    name?: string;
}

export class ArticleCollection extends Collection<Article> {
  filter(kwargs: Partial<ArticleQuery>): this {
    return super.filter(kwargs as Record<string, unknown>);
  }
  sort(...fields: ('title' | '-title' | 'created_at' | '-created_at')[]): this {
    return super.sort(...fields);
  }
  fields(params: { articles?: ('id' | 'title' | 'content' | 'created_at' | 'author' | 'categories')[] | null }): this {
    const converted: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(params)) {
      if (v != null) converted[k] = v;
    }
    return super.fields(converted);
  }
}
export class Article extends Resource {
      static _type = "articles";
      static _attributeTypes: Record<string, string> = {
        'id': 'number',
        'title': 'string',
        'content': 'string',
        'created_at': 'string',
      };
      static _relationshipTypes: Record<string, [string, boolean]> = {
        'author': ['users', false],
        'categories': ['categories', true],
      };
      static _capabilities = new Set(['create', 'delete', 'edit', 'get_many', 'get_one'] as const);
      get title(): string { return this.get('title') as string; }
      set title(value: string) { this.set('title', value); }
      get content(): string { return this.get('content') as string; }
      set content(value: string) { this.set('content', value); }
      get created_at(): string { return this.get('created_at') as string; }
      set created_at(value: string) { this.set('created_at', value); }
      get author(): User { return this.get('author') as User; }
      set author(value: User) { this.set('author', value); }
      get categories(): CategoryCollection | null { return this.get('categories') as CategoryCollection | null; }
      set categories(value: CategoryCollection | null) { this.set('categories', value); }

      static list(): ArticleCollection {
        return super.list() as unknown as ArticleCollection;
      }

      static async get(id: string, ...includes: ("author" | "categories")[]): Promise<Article>;

      static async get(id: string, ...includes: string[]): Promise<Article> {
        return super.get(id as any, ...includes) as unknown as Promise<Article>;
      }

      static async find(query: Partial<ArticleQuery>, ...includes: ("author" | "categories")[]): Promise<Article>;

      static async find(query?: Partial<ArticleQuery>): Promise<Article> {
        return super.find(query as Record<string, unknown>) as unknown as Promise<Article>;
      }

      static async create(props?: ArticleCreate): Promise<Article> {
        return super.create(props as unknown as Record<string, unknown>) as unknown as Promise<Article>;
      }

      async save(props?: ArticleEdit): Promise<void> {
        await super.save(props as Record<string, unknown>);
      }

      async edit(relationship: 'author', resource: User | number): Promise<void>;
      async edit(relationship: string, resource: unknown): Promise<void> {
        await super.edit(relationship, resource);
      }

      async add(relationship: 'categories', ...resources: (Category | number)[]): Promise<void>;
      async add(relationship: string, ...resources: unknown[]): Promise<void> {
        await super.add(relationship, ...resources);
      }

      async remove(relationship: 'categories', ...resources: (Category | number)[]): Promise<void>;
      async remove(relationship: string, ...resources: unknown[]): Promise<void> {
        await super.remove(relationship, ...resources);
      }

      async reset(relationship: 'categories', ...resources: (Category | number)[]): Promise<void>;
      async reset(relationship: string, ...resources: unknown[]): Promise<void> {
        await super.reset(relationship, ...resources);
      }
}

export class UserCollection extends Collection<User> {
  filter(kwargs: Partial<UserQuery>): this {
    return super.filter(kwargs as Record<string, unknown>);
  }
  fields(params: { users?: ('id' | 'username' | 'articles')[] | null }): this {
    const converted: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(params)) {
      if (v != null) converted[k] = v;
    }
    return super.fields(converted);
  }
}
export class User extends Resource {
      static _type = "users";
      static _attributeTypes: Record<string, string> = {
        'id': 'number',
        'username': 'string',
      };
      static _relationshipTypes: Record<string, [string, boolean]> = {
        'articles': ['articles', true],
      };
      static _capabilities = new Set(['get_many', 'get_one'] as const);
      get username(): string { return this.get('username') as string; }
      set username(value: string) { this.set('username', value); }
      get articles(): ArticleCollection | null { return this.get('articles') as ArticleCollection | null; }
      set articles(value: ArticleCollection | null) { this.set('articles', value); }

      static list(): UserCollection {
        return super.list() as unknown as UserCollection;
      }

      static async get(id: string, ...includes: "articles"[]): Promise<User>;

      static async get(id: string, ...includes: string[]): Promise<User> {
        return super.get(id as any, ...includes) as unknown as Promise<User>;
      }

      static async find(query: Partial<UserQuery>, ...includes: "articles"[]): Promise<User>;

      static async find(query?: Partial<UserQuery>): Promise<User> {
        return super.find(query as Record<string, unknown>) as unknown as Promise<User>;
      }
}

export class CategoryCollection extends Collection<Category> {
  filter(kwargs: Partial<CategoryQuery>): this {
    return super.filter(kwargs as Record<string, unknown>);
  }
  fields(params: { categories?: ('id' | 'name' | 'created_at' | 'articles')[] | null }): this {
    const converted: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(params)) {
      if (v != null) converted[k] = v;
    }
    return super.fields(converted);
  }
}
export class Category extends Resource {
      static _type = "categories";
      static _attributeTypes: Record<string, string> = {
        'id': 'number',
        'name': 'string',
        'created_at': 'string | null',
      };
      static _relationshipTypes: Record<string, [string, boolean]> = {
        'articles': ['articles', true],
      };
      static _capabilities = new Set(['create', 'delete', 'get_many'] as const);
      get name(): string { return this.get('name') as string; }
      set name(value: string) { this.set('name', value); }
      get created_at(): string | null { return this.get('created_at') as string | null; }
      set created_at(value: string | null) { this.set('created_at', value); }
      get articles(): ArticleCollection | null { return this.get('articles') as ArticleCollection | null; }
      set articles(value: ArticleCollection | null) { this.set('articles', value); }

      static list(): CategoryCollection {
        return super.list() as unknown as CategoryCollection;
      }

      static async find(query: Partial<CategoryQuery>, ...includes: "articles"[]): Promise<Category>;

      static async find(query?: Partial<CategoryQuery>): Promise<Category> {
        return super.find(query as Record<string, unknown>) as unknown as Promise<Category>;
      }

      static async create(props?: CategoryCreate): Promise<Category> {
        return super.create(props as unknown as Record<string, unknown>) as unknown as Promise<Category>;
      }
}
