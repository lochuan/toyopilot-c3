<script setup lang="ts">
/** 显示页的开机画面卡片：看当前画面 → 选图预览 → 写入 splash 分区 / 恢复修改前的画面。
 *
 * 选好的图先在浏览器里画成 2160×1080 横图（lib/splash.ts），预览即开机所见；
 * 写入和恢复都限停车，重启后生效。
 */
import { onMounted, onUnmounted, ref } from "vue";
import { ImagePlus, Loader2, RotateCcw, Upload } from "lucide-vue-next";
import { api } from "@/lib/api";
import type { SplashStatus } from "@/lib/schema";
import { renderSplashJpeg } from "@/lib/splash";
import { toast } from "@/lib/store";
import Button from "./ui/Button.vue";

const status = ref<SplashStatus | null>(null);
const loadError = ref("");
const pending = ref<{ blob: Blob; url: string } | null>(null);
const busy = ref<"" | "render" | "write" | "restore">("");
const fileInput = ref<HTMLInputElement | null>(null);

async function load(): Promise<void> {
  try {
    status.value = await api.splash();
    loadError.value = "";
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e);
  }
}

function clearPending(): void {
  if (pending.value) URL.revokeObjectURL(pending.value.url);
  pending.value = null;
}

async function onPick(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = ""; // 允许重选同一张
  if (!file) return;
  busy.value = "render";
  try {
    const blob = await renderSplashJpeg(file);
    clearPending();
    pending.value = { blob, url: URL.createObjectURL(blob) };
  } catch {
    toast("无法读取这张图片", "error");
  } finally {
    busy.value = "";
  }
}

async function run(kind: "write" | "restore"): Promise<void> {
  if (busy.value) return;
  busy.value = kind;
  try {
    status.value = kind === "write" ? await api.putSplash(pending.value!.blob) : await api.restoreSplash();
    clearPending();
    toast(kind === "write" ? "开机画面已写入，重启后生效" : "已恢复修改前的开机画面，重启后生效", "ok");
  } catch (e) {
    toast(e instanceof Error ? e.message : "操作失败", "error");
  } finally {
    busy.value = "";
  }
}

onMounted(() => void load());
onUnmounted(clearPending);
</script>

<template>
  <section class="sl-card px-5 py-4">
    <h2 class="mb-3 text-[13px] font-semibold uppercase tracking-wider text-sl-text-3">开机画面</h2>

    <p v-if="loadError" class="rounded-lg bg-sl-danger/10 px-3 py-2 text-[13px] text-sl-danger">
      读取开机画面失败：{{ loadError }}
    </p>
    <div v-else-if="!status" class="grid h-32 place-items-center">
      <Loader2 class="size-6 animate-spin text-sl-text-3" />
    </div>

    <template v-else>
      <div class="grid gap-3" :class="pending ? 'sm:grid-cols-2' : ''">
        <figure class="flex flex-col gap-1.5">
          <img :src="status.preview" alt="当前开机画面" class="aspect-[2/1] w-full rounded-lg bg-black object-contain ring-1 ring-sl-border" />
          <figcaption class="text-[12px] text-sl-text-3">当前{{ status.customized ? "（已自定义）" : "" }}</figcaption>
        </figure>
        <figure v-if="pending" class="flex flex-col gap-1.5">
          <img :src="pending.url" alt="待写入的开机画面" class="aspect-[2/1] w-full rounded-lg bg-black object-contain ring-1 ring-sl-accent" />
          <figcaption class="text-[12px] text-sl-text-3">待写入</figcaption>
        </figure>
      </div>

      <div class="mt-4 flex flex-wrap gap-2">
        <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onPick" />
        <Button :disabled="!!busy" @click="fileInput?.click()">
          <Loader2 v-if="busy === 'render'" class="animate-spin" /><ImagePlus v-else />
          选择图片
        </Button>
        <template v-if="pending">
          <Button variant="accent" :disabled="!status.offroad || !!busy" @click="run('write')">
            <Loader2 v-if="busy === 'write'" class="animate-spin" /><Upload v-else />
            写入
          </Button>
          <Button variant="ghost" :disabled="!!busy" @click="clearPending">取消</Button>
        </template>
        <Button v-if="status.customized && !pending" variant="danger" :disabled="!status.offroad || !!busy"
                @click="run('restore')">
          <Loader2 v-if="busy === 'restore'" class="animate-spin" /><RotateCcw v-else />
          恢复修改前的画面
        </Button>
      </div>

      <p class="mt-3 rounded-lg bg-sl-surface-2 px-3 py-2 text-[13px] text-sl-text-3">
        建议 2160×1080 横图，其他尺寸等比缩放、四周留黑。重启后生效{{ status.offroad ? "" : "；写入与恢复限停车（offroad）操作" }}。
      </p>
    </template>
  </section>
</template>
