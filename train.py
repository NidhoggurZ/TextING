from __future__ import division
from __future__ import print_function

import time
import tensorflow as tf
from sklearn import metrics
import pickle as pkl

from utils import *
from models import GCN, MLP

# Set random seed
#seed = 123
#np.random.seed(seed)
#tf.set_random_seed(seed)

# Settings
flags = tf.app.flags
FLAGS = flags.FLAGS
flags.DEFINE_string('dataset', 'mr', 'Dataset string.')  # 'mr','ohsumed','R8','R52'
flags.DEFINE_string('model', 'gcn', 'Model string.') 
flags.DEFINE_float('learning_rate', 0.01, 'Initial learning rate.')
flags.DEFINE_integer('epochs', 200, 'Number of epochs to train.')
flags.DEFINE_integer('input_dim', 300, 'Dimension of input')
flags.DEFINE_integer('hidden1', 32, 'Number of units in hidden layer.') # 32, 64, 96
flags.DEFINE_float('dropout', 0.5, 'Dropout rate (1 - keep probability).')
flags.DEFINE_float('weight_decay', 0, 'Weight for L2 loss on embedding matrix.')
flags.DEFINE_integer('early_stopping', 1000, 'Tolerance for early stopping (# of epochs).')
flags.DEFINE_integer('max_degree', 3, 'Maximum Chebyshev polynomial degree.')

# Load data
train_adj, train_feature, train_y, val_adj, val_feature, val_y, test_adj, test_feature, test_y = load_data(FLAGS.dataset)

print('dataset', FLAGS.dataset, 'hidden', FLAGS.hidden1, 'dropout', FLAGS.dropout)

# Some preprocessing
#features = preprocess_features(features)
train_adj, train_mask = preprocess_adj(train_adj)
train_feature = preprocess_features(train_feature)
val_adj, val_mask = preprocess_adj(val_adj)
val_feature = preprocess_features(val_feature)
test_adj, test_mask = preprocess_adj(test_adj)
test_feature = preprocess_features(test_feature)


if FLAGS.model == 'gcn':
    #support = [preprocess_adj(adj)]
    #num_supports = len(support)
    num_supports = 1
    model_func = GCN
elif FLAGS.model == 'gcn_cheby':
    #support = chebyshev_polynomials(adj, FLAGS.max_degree)
    num_supports = 1 + FLAGS.max_degree
    model_func = GCN
elif FLAGS.model == 'dense':
    #support = [preprocess_adj(adj)]  # Not used
    num_supports = 1
    model_func = MLP
else:
    raise ValueError('Invalid argument for model: ' + str(FLAGS.model))

# Define placeholders
placeholders = {
    'support': tf.placeholder(tf.float32, shape=(None, None, None)),
    'features': tf.placeholder(tf.float32, shape=(None, None, FLAGS.input_dim)),
    'mask': tf.placeholder(tf.float32, shape=(None, None, 1)),
    'labels': tf.placeholder(tf.float32, shape=(None, train_y.shape[1])),
    'dropout': tf.placeholder_with_default(0., shape=()),
    'num_features_nonzero': tf.placeholder(tf.int32)  # helper variable for sparse dropout
}


#label smoothing
# label_smoothing = 0.1
# num_classes = y_train.shape[1]
# y_train = (1.0 - label_smoothing) * y_train + label_smoothing / num_classes


# Create model
model = model_func(placeholders, input_dim=FLAGS.input_dim, logging=True)

# Initialize session
sess = tf.Session()

#merged = tf.summary.merge_all()
#writer = tf.summary.FileWriter('logs/', sess.graph)

# Define model evaluation function
def evaluate(features, support, mask, labels, placeholders):
    t_test = time.time()
    feed_dict_val = construct_feed_dict(features, support, mask, labels, placeholders)
    outs_val = sess.run([model.loss, model.accuracy, model.embeddings, model.preds, model.labels], feed_dict=feed_dict_val)
    return outs_val[0], outs_val[1], (time.time() - t_test), outs_val[2], outs_val[3], outs_val[4]


# Init variables
sess.run(tf.global_variables_initializer())

cost_val = []
best_acc = 0
best_epoch = 0
best_cost = 0
test_doc_embeddings = None
preds = None
labels = None
print('train start...')
# Train model
for epoch in range(FLAGS.epochs):
    t = time.time()
    # Construct feed dictionary
    feed_dict = construct_feed_dict(train_feature, train_adj, train_mask, train_y, placeholders)
    feed_dict.update({placeholders['dropout']: FLAGS.dropout})

    # Training step
    outs = sess.run([model.opt_op, model.loss, model.accuracy], feed_dict=feed_dict)

    # Validation
    cost, acc, duration, _, _, _ = evaluate(val_feature, val_adj, val_mask, val_y, placeholders)
    cost_val.append(cost)
    
    test_cost, test_acc, test_duration, embeddings, p, labels = evaluate(test_feature, test_adj, test_mask, test_y, placeholders)
    if test_acc>best_acc:
        best_acc = test_acc
        best_epoch = epoch
        best_cost = test_cost
        test_doc_embeddings = embeddings
        preds = p

    # Print results
    print("Epoch:", '%04d' % (epoch + 1), "train_loss=", "{:.5f}".format(outs[1]),
          "train_acc=", "{:.5f}".format(outs[2]), "val_loss=", "{:.5f}".format(cost),
          "val_acc=", "{:.5f}".format(acc), "test_acc=", "{:.5f}".format(test_acc), "time=", "{:.5f}".format(time.time() - t),"best_acc=", "{:.5f}".format(best_acc))

    if epoch > FLAGS.early_stopping and cost_val[-1] > np.mean(cost_val[-(FLAGS.early_stopping+1):-1]):
        print("Early stopping...")
        break

print("Optimization Finished!")

# Testing
print('Best epoch:', best_epoch)
print("Test set results:", "cost=", "{:.5f}".format(best_cost),
      "accuracy=", "{:.5f}".format(best_acc))

print("Test Precision, Recall and F1-Score...")
print(metrics.classification_report(labels, preds, digits=4))
print("Macro average Test Precision, Recall and F1-Score...")
print(metrics.precision_recall_fscore_support(labels, preds, average='macro'))
print("Micro average Test Precision, Recall and F1-Score...")
print(metrics.precision_recall_fscore_support(labels, preds, average='micro'))

'''
doc_vectors = []
for i in range(len(test_doc_embeddings)):
    doc_vector = test_doc_embeddings[i]
    doc_vector_str = ' '.join([str(x) for x in doc_vector])
    doc_vectors.append(str(np.argmax(test_y[i])) + ' ' + doc_vector_str)

doc_embeddings_str = '\n'.join(doc_vectors)
f = open('data/' + FLAGS.dataset + '_doc_vectors.txt', 'w')
f.write(doc_embeddings_str)
f.close()
'''
