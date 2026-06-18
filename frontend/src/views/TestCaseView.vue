<template>
  <div class="case-page">
    <section class="glass-card panel">
      <div class="section-heading">
        <div>
          <h2>测试用例管理</h2>
          <p>管理 baseline、contract、negative、metamorphic 等测试用例。</p>
        </div>
        <div>
          <el-button type="primary" :loading="generating" @click="generate">自动生成用例</el-button>
          <el-button @click="openEditor()">手动新增</el-button>
        </div>
      </div>

      <el-steps v-if="generating" :active="activeStep" finish-status="success" class="steps">
        <el-step v-for="step in steps" :key="step" :title="step" />
      </el-steps>

      <el-table :data="store.testCases">
        <el-table-column prop="case_id" label="case_id" width="150" />
        <el-table-column prop="case_type" label="case_type" width="140" />
        <el-table-column prop="objective" label="objective" min-width="320" />
        <el-table-column prop="oracle_type" label="oracle_type" width="170" />
        <el-table-column prop="enabled" label="enabled" width="110">
            <template #default="{ row }"><el-switch v-model="row.enabled" @change="placeholderAction" /></template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }"><el-button size="small" @click="openEditor(row)">编辑</el-button></template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="dialogVisible" title="测试用例" width="620px">
      <el-form label-position="top">
        <el-form-item label="case_id"><el-input v-model="form.case_id" /></el-form-item>
        <el-form-item label="case_type"><el-select v-model="form.case_type"><el-option v-for="item in caseTypes" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="objective"><el-input v-model="form.objective" type="textarea" /></el-form-item>
        <el-form-item label="oracle_type"><el-select v-model="form.oracle_type"><el-option v-for="item in oracleTypes" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="enabled"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import type { TestCase } from '@/types/domain'

const store = useAppStore()
const generating = ref(false)
const activeStep = ref(0)
const dialogVisible = ref(false)
const steps = ['需求抽取', '模式选择', '用例生成', '校验', '冻结']
const caseTypes = ['baseline', 'contract', 'negative', 'metamorphic', 'tool_error']
const oracleTypes = ['rule_oracle', 'contract_oracle', 'llm_judge', 'metamorphic_oracle']
const form = reactive<TestCase>(emptyCase())

function emptyCase(): TestCase {
  return { id: `tc-${Date.now()}`, project_id: store.currentProjectId, case_id: 'CUSTOM_001', case_type: 'baseline', objective: '', oracle_type: 'rule_oracle', enabled: true }
}

const generate = async () => {
  generating.value = true
  activeStep.value = 0
  const timer = window.setInterval(() => {
    activeStep.value = Math.min(activeStep.value + 1, steps.length)
  }, 420)
  await wait(1800)
  window.clearInterval(timer)
  activeStep.value = steps.length
  window.setTimeout(() => (generating.value = false), 500)
  placeholderAction()
}

const openEditor = (item?: TestCase) => {
  Object.assign(form, item ? structuredClone(item) : emptyCase())
  dialogVisible.value = true
}

const save = async () => {
  dialogVisible.value = false
  placeholderAction()
}

const placeholderAction = () => {
  ElMessage.warning('演示版本：当前展示的是已完成的真实测试数据，该操作未接入实时执行')
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
</script>

<style scoped>
.panel {
  padding: 18px;
}

.steps {
  margin: 18px 0 24px;
}
</style>
