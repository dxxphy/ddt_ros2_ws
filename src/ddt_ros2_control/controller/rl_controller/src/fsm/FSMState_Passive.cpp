// Copyright (c) 2023 Direct Drive Technology Co., Ltd. All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "rl_controller/fsm/FSMState_Passive.h"

FSMState_Passive::FSMState_Passive(std::shared_ptr<ControlFSMData> data) : FSMState(data, "idle") {}

void FSMState_Passive::enter()
{
  hold_jpos_initialized_ = false;
}

void FSMState_Passive::run()
{
  _data->low_cmd->zero();
  const auto & joint_pd_target = _data->params->joint_pd_params.target_jpos;
  const auto & joint_pd_kp = _data->params->joint_pd_params.joint_kp;
  const auto & joint_pd_kd = _data->params->joint_pd_params.joint_kd;

  if (!joint_pd_target.empty()) {
    _data->low_cmd->qd = vectorToEigen(joint_pd_target);
  } else {
    if (!hold_jpos_initialized_) {
      hold_jpos_ = _data->low_state->q;
      hold_jpos_initialized_ = true;
    }
    _data->low_cmd->qd = hold_jpos_;
  }
  _data->low_cmd->qd_dot.setZero();
  if (!joint_pd_kp.empty() && !joint_pd_kd.empty()) {
    _data->low_cmd->kp = vectorToEigen(joint_pd_kp);
    _data->low_cmd->kd = vectorToEigen(joint_pd_kd);
  } else {
    for (int i = 0; i < _data->low_cmd->kd.size(); i++) {
      _data->low_cmd->kp(i) = 25;
      _data->low_cmd->kd(i) = 1;
    }
    for (auto i : _data->params->hip_indices) {
      _data->low_cmd->kp(i) = 10;
    }
  }
  for (auto i : _data->params->wheel_indices) {
    _data->low_cmd->kp(i) = 0;
    _data->low_cmd->kd(i) = 0;
    _data->low_cmd->qd(i) = 0;
  }
  // if(!_data->params_->ee_name_.empty()){
  //   Eigen::VectorXd kp_joint, kd_joint;
  //   kp_joint.setZero(6);
  //   kd_joint.setZero(6);
  //   kp_joint << 100, 100, 10, 1, 1, 1;
  //   // kd_joint << 1, 1, 1, 0.1, 0.1, 0.1;
  //   _data->low_cmd_->tau_cmd.tail(6) = kp_joint.cwiseProduct(-_data->low_state_->q.tail(6)) + kd_joint.cwiseProduct(-_data->low_state_->dq.tail(6));
  //   PRINT_MAT(_data->low_state_->dq.tail(6));
  // }
  // _data->_stateEstimator->run();
}

void FSMState_Passive::exit() {}

std::string FSMState_Passive::checkTransition()
{
  this->_nextStateName = this->_stateName;

  // Switch FSM control mode
  auto desire_state = _data->rc_data->fsm_name_;
  if (desire_state == "transform_up") {
    this->_nextStateName = "transform_up";
  } else if (desire_state == "joint_pd") {
    this->_nextStateName = "joint_pd";
  } else if (desire_state.find("rl_") == 0) {
    try {
      size_t number = std::stoi(desire_state.substr(3));
      if (number < _data->params->rl_policy_names.size()) {
        this->_nextStateName = _data->params->rl_policy_names[number];
      }
    } catch (const std::exception & e) {
      std::cerr << "Invalid number format in " << desire_state << std::endl;
    }
  }
  return this->_nextStateName;
}
