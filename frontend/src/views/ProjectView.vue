<template>
  <div class="project-page">
    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>项目管理</h2>
          <p>管理被测智能体应用的适配器、启动命令、模型和 Oracle 配置。</p>
        </div>
        <el-button type="primary" @click="openCreate">新建项目</el-button>
      </div>
      <el-table :data="store.projects" @row-click="selectProject">
        <el-table-column prop="name" label="name" min-width="220" />
        <el-table-column prop="adapter_type" label="adapter_type" />
        <el-table-column prop="status" label="status">
          <template #default="{ row }"><el-tag effect="dark">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="created_at" label="created_at" />
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" @click.stop="editProject(row)">编辑</el-button>
            <el-button size="small" type="primary" :loading="analyzing" @click.stop="analyze(row.id)">分析项目</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-if="selected?.profile" class="profile-grid">
      <article class="glass-card profile-card">
        <h3>Agents</h3>
        <el-tag v-for="item in selected.profile.agents" :key="item" effect="dark" type="primary">{{ item }}</el-tag>
      </article>
      <article class="glass-card profile-card">
        <h3>Tools</h3>
        <el-tag v-for="item in selected.profile.tools" :key="item" effect="dark" type="warning">{{ item }}</el-tag>
      </article>
      <article class="glass-card profile-card wide">
        <h3>Requirements</h3>
        <div class="req-list">
          <span v-for="item in selected.profile.requirements" :key="item">{{ item }}</span>
        </div>
      </article>
    </section>

    <el-dialog v-model="dialogVisible" title="项目配置" width="720px">
      <el-form label-position="top">
        <el-form-item label="项目名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="adapter_type">
          <el-select v-model="form.config.adapter_type">
            <el-option label="autogen" value="autogen" />
            <el-option label="generic_cli" value="generic_cli" />
            <el-option label="generic_http" value="generic_http" />
          </el-select>
        </el-form-item>
        <el-form-item label="project_path"><el-input v-model="form.config.project_path" /></el-form-item>
        <el-form-item label="command_template"><el-input v-model="form.config.command_template" /></el-form-item>
        <el-form-item label="http_url"><el-input v-model="form.config.http_url" /></el-form-item>
        <el-form-item label="timeout"><el-input-number v-model="form.config.timeout" :min="1" /></el-form-item>
        <el-form-item label="model_config"><el-input v-model="form.config.model_config" type="textarea" /></el-form-item>
        <el-form-item label="oracle_config"><el-input v-model="form.config.oracle_config" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import type { Project } from '@/types/domain'

const store = useAppStore()
const selectedId = ref('p-autogen-001')
const dialogVisible = ref(false)
const analyzing = ref(false)
const form = reactive<Project>(emptyProject())
const selected = computed(() => store.projects.find((item) => item.id === selectedId.value) ?? store.projects[0])

function emptyProject(): Project {
  return {
    id: `p-${Date.now()}`,
    name: 'New Agent Project',
    adapter_type: 'autogen',
    status: 'draft',
    created_at: new Date().toISOString().slice(0, 16).replace('T', ' '),
    config: {
      adapter_type: 'autogen',
      project_path: '',
      command_template: '',
      http_url: '',
      timeout: 120,
      model_config: '',
      oracle_config: ''
    }
  }
}

const selectProject = (row: Project) => {
  selectedId.value = row.id
}

const openCreate = () => {
  Object.assign(form, emptyProject())
  dialogVisible.value = true
}

const editProject = (project: Project) => {
  Object.assign(form, structuredClone(project))
  dialogVisible.value = true
}

const save = async () => {
  form.adapter_type = form.config.adapter_type
  await store.saveProject(structuredClone(form))
  dialogVisible.value = false
  ElMessage.success('项目配置已保存')
}

const analyze = async (id: string) => {
  analyzing.value = true
  await store.analyzeProject(id)
  analyzing.value = false
  selectedId.value = id
  ElMessage.success('项目分析完成，已生成 SystemProfile 摘要')
}
</script>

<style scoped>
.project-page,
.profile-grid {
  display: grid;
  gap: 16px;
}

.panel,
.profile-card {
  padding: 18px;
}

.profile-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.profile-card {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.profile-card h3 {
  flex-basis: 100%;
  margin: 0;
}

.profile-card.wide {
  grid-column: 1 / -1;
}

.req-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
}

.req-list span {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.78);
}
</style>
