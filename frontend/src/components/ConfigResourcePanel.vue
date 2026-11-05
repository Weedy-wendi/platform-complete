<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { apiFetch, idempotencyKey } from "@/api/client";
import { describeError } from "@/api/errors";
import PermissionGate from "@/components/PermissionGate.vue";
import {
  configText,
  normalizeConfigItems,
  parseConfigText,
  type ConfigItem,
} from "@/utils/config";

const props = defineProps<{
  endpoint: string;
  resource: "evaluators" | "suites" | "targets";
}>();

const { t } = useI18n();
const items = ref<ConfigItem[]>([]);
const loading = ref(false);
const loadError = ref<unknown>(null);
const saveError = ref<unknown>(null);
const formError = ref("");
const saving = ref(false);
const dialogVisible = ref(false);
const editing = ref(false);
const form = reactive({
  id: "",
  name: "",
  description: "",
  configText: "",
});

const resourceLabel = computed(() => {
  const keys = {
    evaluators: "config.tabEvaluators",
    suites: "config.tabSuites",
    targets: "config.tabTargets",
  } as const;
  return t(keys[props.resource]);
});
const loadErrorText = computed(() => (loadError.value ? describeError(loadError.value, t) : ""));
const saveErrorText = computed(() => (saveError.value ? describeError(saveError.value, t) : ""));
const dialogTitle = computed(() =>
  t(editing.value ? "config.editTitle" : "config.createTitle", { resource: resourceLabel.value }),
);

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    items.value = normalizeConfigItems(await apiFetch<unknown>(props.endpoint));
  } catch (exc) {
    loadError.value = exc;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editing.value = false;
  saveError.value = null;
  formError.value = "";
  form.id = "";
  form.name = "";
  form.description = "";
  form.configText = "";
  dialogVisible.value = true;
}

function openEdit(item: ConfigItem) {
  editing.value = true;
  saveError.value = null;
  formError.value = "";
  form.id = item.id;
  form.name = item.name;
  form.description = item.description;
  form.configText = configText(item.config);
  dialogVisible.value = true;
}

async function save() {
  formError.value = "";
  saveError.value = null;
  if (!form.name.trim()) {
    formError.value = t("config.nameRequired");
    return;
  }
  const parsed = parseConfigText(form.configText);
  if (!parsed.ok) {
    formError.value = t("config.invalidConfig");
    return;
  }

  saving.value = true;
  try {
    const body: Record<string, unknown> = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      config: parsed.value,
    };
    if (editing.value) body.id = form.id;
    await apiFetch(props.endpoint, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify(body),
    });
    dialogVisible.value = false;
    await load();
  } catch (exc) {
    saveError.value = exc;
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="config-panel">
    <div class="list-toolbar">
      <el-button :loading="loading" @click="load">{{ t("common.refresh") }}</el-button>
      <PermissionGate scope="evaluators:write">
        <template #fallback>
          <span class="muted">{{ t("config.writeForbidden") }}</span>
        </template>
        <el-button type="primary" data-test="config-create" @click="openCreate">
          {{ t("config.create") }}
        </el-button>
      </PermissionGate>
    </div>

    <el-alert v-if="loadErrorText" :title="loadErrorText" type="error" show-icon />

    <el-table v-if="items.length" :data="items" class="table" data-test="config-table">
      <el-table-column prop="id" :label="'ID'" show-overflow-tooltip />
      <el-table-column prop="name" :label="t('config.name')" show-overflow-tooltip />
      <el-table-column prop="description" :label="t('config.description')" show-overflow-tooltip />
      <el-table-column :label="t('config.version')" width="120" data-test="config-version">
        <template #default="{ row }">
          {{ row.version || t("common.notAvailable") }}
        </template>
      </el-table-column>
      <el-table-column v-if="resource === 'evaluators'" :label="t('config.kind')" width="120">
        <template #default="{ row }">
          {{ row.kind || t("common.notAvailable") }}
        </template>
      </el-table-column>
      <el-table-column :label="t('config.actions')" width="140">
        <template #default="{ row }">
          <PermissionGate scope="evaluators:write">
            <el-button link type="primary" data-test="config-edit" @click="openEdit(row)">
              {{ t("config.edit") }}
            </el-button>
          </PermissionGate>
        </template>
      </el-table-column>
    </el-table>
    <p v-else-if="!loading && !loadErrorText" class="empty">{{ t("config.empty") }}</p>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px">
      <el-form label-position="top">
        <el-form-item :label="t('config.name')">
          <el-input v-model="form.name" data-test="config-name" />
        </el-form-item>
        <el-form-item :label="t('config.description')">
          <el-input v-model="form.description" data-test="config-description" />
        </el-form-item>
        <el-form-item :label="t('config.config')">
          <el-input
            v-model="form.configText"
            type="textarea"
            :rows="8"
            data-test="config-json"
            :placeholder="t('config.configHint')"
          />
        </el-form-item>
      </el-form>

      <el-alert v-if="formError" :title="formError" type="error" show-icon />
      <el-alert v-if="saveErrorText" :title="saveErrorText" type="error" show-icon />

      <template #footer>
        <el-button @click="dialogVisible = false">{{ t("common.cancel") }}</el-button>
        <PermissionGate scope="evaluators:write">
          <el-button type="primary" :loading="saving" data-test="config-save" @click="save">
            {{ saving ? t("config.saving") : t("config.save") }}
          </el-button>
        </PermissionGate>
      </template>
    </el-dialog>
  </section>
</template>
